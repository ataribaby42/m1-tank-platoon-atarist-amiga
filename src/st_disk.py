"""Read and update the FAT12 Atari ST source image, preserving other files."""
from dataclasses import dataclass
import struct


@dataclass(frozen=True)
class Entry:
    path: str
    offset: int
    attributes: int
    cluster: int
    size: int


class STDisk:
    def __init__(self, data):
        self.data = bytearray(data)
        self.sector = struct.unpack_from('<H', data, 11)[0]
        self.cluster_sectors = data[13]
        self.reserved, self.fats, self.root_entries, self.sectors = struct.unpack_from('<HBHH', data, 14)
        self.fat_sectors = struct.unpack_from('<H', data, 22)[0]
        assert self.sector == 512 and self.cluster_sectors == 2 and self.fats == 2
        assert len(data) == self.sectors * self.sector
        self.cluster_size = self.sector * self.cluster_sectors
        self.fat_start = self.reserved * self.sector
        self.fat_size = self.fat_sectors * self.sector
        self.root_start = self.fat_start + self.fats * self.fat_size
        self.data_start = self.root_start + ((self.root_entries * 32 + self.sector - 1) // self.sector) * self.sector
        self.cluster_count = (len(data) - self.data_start) // self.cluster_size
        assert data[self.fat_start:self.fat_start+self.fat_size] == data[self.fat_start+self.fat_size:self.root_start]

    def fat(self, cluster):
        offset = self.fat_start + cluster * 3 // 2
        value = struct.unpack_from('<H', self.data, offset)[0]
        return (value >> 4 if cluster & 1 else value) & 0xfff

    def set_fat(self, cluster, value):
        for copy in range(self.fats):
            offset = self.fat_start + copy * self.fat_size + cluster * 3 // 2
            before = struct.unpack_from('<H', self.data, offset)[0]
            after = (before & 0xf) | (value << 4) if cluster & 1 else (before & 0xf000) | value
            struct.pack_into('<H', self.data, offset, after)

    def chain(self, cluster):
        result = []
        while cluster >= 2 and cluster < 0xff8:
            assert cluster < self.cluster_count + 2 and cluster not in result
            result.append(cluster)
            cluster = self.fat(cluster)
        assert cluster >= 0xff8 or (not result and cluster == 0)
        return result

    def cluster_offset(self, cluster):
        assert 2 <= cluster < self.cluster_count + 2
        return self.data_start + (cluster - 2) * self.cluster_size

    def entries(self):
        result = []
        def walk(offsets, parent=''):
            for offset in offsets:
                row = self.data[offset:offset+32]
                if row[0] == 0:
                    return
                if row[0] == 0xe5 or row[11] & 8 or row[0] == 46:
                    continue
                name = bytes(row[:8]).decode('ascii').rstrip(' \x00')
                extension = bytes(row[8:11]).decode('ascii').rstrip(' \x00')
                path = parent + name + ('.'+extension if extension else '')
                entry = Entry(path, offset, row[11], struct.unpack_from('<H', row, 26)[0],
                              struct.unpack_from('<I', row, 28)[0])
                result.append(entry)
                if row[11] & 16:
                    walk([self.cluster_offset(c)+i for c in self.chain(entry.cluster)
                          for i in range(0, self.cluster_size, 32)], path+'/')
        walk(range(self.root_start, self.root_start+self.root_entries*32, 32))
        return result

    def entry(self, path):
        return next(e for e in self.entries() if e.path.casefold() == path.casefold())

    def read(self, path):
        e = self.entry(path)
        assert not e.attributes & 16
        data = b''.join(bytes(self.data[self.cluster_offset(c):self.cluster_offset(c)+self.cluster_size])
                        for c in self.chain(e.cluster))
        assert len(data) >= e.size
        return data[:e.size]

    def snapshot(self):
        return {e.path: self.read(e.path) for e in self.entries() if not e.attributes & 16}

    def replace(self, path, payload):
        e = self.entry(path)
        assert not e.attributes & 16
        before = self.snapshot()
        old = self.chain(e.cluster)
        needed = (len(payload) + self.cluster_size - 1) // self.cluster_size
        available = old + [c for c in range(2, self.cluster_count+2) if self.fat(c) == 0]
        if needed > len(available):
            raise ValueError(f'Not enough disk space for {path}: need {needed}, available {len(available)} clusters')
        selected = available[:needed]
        for c in old:
            self.set_fat(c, 0)
        for index, c in enumerate(selected):
            self.set_fat(c, selected[index+1] if index+1 < needed else 0xfff)
            offset = self.cluster_offset(c)
            self.data[offset:offset+self.cluster_size] = payload[index*self.cluster_size:(index+1)*self.cluster_size].ljust(self.cluster_size, b'\0')
        struct.pack_into('<H', self.data, e.offset+26, selected[0] if selected else 0)
        struct.pack_into('<I', self.data, e.offset+28, len(payload))
        assert self.read(path) == payload
        assert self.snapshot() == {**before, e.path: bytes(payload)}
