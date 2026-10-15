"""TOS executable parsing and relocation-table serialization."""
import struct


class TOSExecutable:
    def __init__(self, blob):
        assert blob[:2] == b'\x60\x1a' and len(blob) >= 28
        self.header = bytearray(blob[:28])
        self.text_size, self.data_size, self.bss_size, symbol_size = struct.unpack_from('>4I', blob, 2)
        self.image = bytearray(blob[28:28+self.text_size+self.data_size])
        self.symbols = blob[28+len(self.image):28+len(self.image)+symbol_size]
        assert len(self.symbols) == symbol_size
        assert struct.unpack_from('>H', blob, 26)[0] == 0, 'Absolute TOS executable unsupported'
        cursor = 28 + len(self.image) + symbol_size
        first = struct.unpack_from('>I', blob, cursor)[0]
        cursor += 4
        self.relocations = []
        if first:
            self.relocations.append(first)
            address = first
            while True:
                delta = blob[cursor]
                cursor += 1
                if not delta:
                    break
                address += 254 if delta == 1 else delta
                if delta != 1:
                    self.relocations.append(address)
        self.trailing = blob[cursor:]
        assert all(p % 2 == 0 and 0 <= p <= len(self.image)-4 for p in self.relocations)

    def serialize(self):
        assert len(self.image) == self.text_size + self.data_size
        struct.pack_into('>4I', self.header, 2, self.text_size, self.data_size, self.bss_size, len(self.symbols))
        reloc = sorted(set(self.relocations))
        table = bytearray(struct.pack('>I', reloc[0] if reloc else 0))
        for previous, address in zip(reloc, reloc[1:]):
            delta = address - previous
            assert delta >= 2 and not delta & 1
            while delta > 254:
                table.append(1)
                delta -= 254
            table.append(delta)
        if reloc:
            table.append(0)
        return bytes(self.header + self.image + self.symbols + table + self.trailing)

    def relocated(self, base):
        result = bytearray(self.image)
        for p in self.relocations:
            struct.pack_into('>I', result, p, (struct.unpack_from('>I', result, p)[0]+base) & 0xffffffff)
        return bytes(result)
