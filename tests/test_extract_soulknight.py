import base64
import json
import struct

import extract_soulknight as E

HEADER = b'"Key"\t"Type"\t"English"\t"Chinese"\n'


def xor(data, key):
    return bytes(b ^ key[i % len(key)] for i, b in enumerate(data))


# --------------------------------------------------------------------------- parse_tsv


def test_parse_tsv_plain_rows():
    text = '"Key"\t"Type"\t"English"\t"Chinese"\n"1"\t"t"\t"Sword"\t"剑"\n"2"\t"t"\t"Bow"\t"弓"'
    header, rows = E.parse_tsv(text)
    assert header == ['Key', 'Type', 'English', 'Chinese']
    assert rows == [['1', 't', 'Sword', '剑'], ['2', 't', 'Bow', '弓']]


def test_parse_tsv_keeps_newlines_and_quotes_inside_cells():
    # The reason csv.reader cannot be used: a cell holds a raw newline and a doubled quote.
    text = (
        '"Key"\t"Type"\t"English"\t"Chinese"\n'
        '"1"\t"t"\t"line one\nline "two" ""q"""\t"x"\n'
        '"2"\t"t"\t"next"\t"y"'
    )
    _, rows = E.parse_tsv(text)
    assert rows[0][2] == 'line one\nline "two" "q"'
    assert rows[1][0] == '2'


def test_parse_tsv_drops_rows_with_wrong_cell_count():
    text = '"Key"\t"Type"\t"English"\n"1"\t"t"\t"ok"\n"2"\t"t"\t"a"\t"extra"'
    _, rows = E.parse_tsv(text)
    assert [r[0] for r in rows] == ['1']


def test_parse_tsv_handles_crlf():
    text = '"Key"\t"Type"\t"English"\r\n"1"\t"t"\t"a"\r\n"2"\t"t"\t"b"'
    _, rows = E.parse_tsv(text)
    assert [r[2] for r in rows] == ['a', 'b']


# --------------------------------------------------------------------------- deobfuscate


def test_deobfuscate_recovers_repeating_key():
    plain = HEADER * 12 + '"9"\t"t"\t"hello"\t"你好"\n'.encode()
    key = bytes(range(1, 8))  # period 7, shorter than the known header
    header = plain[: len(HEADER) * 12]
    assert E.deobfuscate(xor(plain, key), header) == plain


def test_deobfuscate_returns_none_for_non_repeating_stream():
    plain = HEADER * 2
    noise = bytes((i * 131 + 7) % 251 for i in range(len(plain)))
    assert E.deobfuscate(noise, plain[:20]) is None


# --------------------------------------------------------------------------- textasset_bytes


class FakeObj:
    def __init__(self, raw):
        self.raw = raw

    def get_raw_data(self):
        return self.raw


def test_textasset_bytes_reads_name_and_padded_payload():
    name, payload = b'loc_s1', b'\xff\xfe raw bytes'
    raw = struct.pack('<I', len(name)) + name + b'\0\0'  # pad 4+6 -> 12
    raw += struct.pack('<I', len(payload)) + payload
    assert E.textasset_bytes(FakeObj(raw)) == ('loc_s1', payload)


# --------------------------------------------------------------------------- icon helpers


def test_icon_candidates_has_no_equipment_arithmetic():
    names = list(E.icon_candidates(101643))
    assert names[0] == 'ItemIcon_101643'
    # The removed rule would have produced ItemIcon_1643000. It must never come back.
    assert 'ItemIcon_1643000' not in names


def test_sprite_folder():
    assert E.sprite_folder('ItemIcon_CL_S1_000') == 'ItemIcon_CL'
    assert E.sprite_folder('EBF_SCATTERING', forced='EBF') == 'EBF'
    assert E.sprite_folder('1234') == 'misc'
    assert E.icon_folder('ItemIcon_7501000') == 'ItemIcon/ItemIcon_7501000.png'


# --------------------------------------------------------------------------- catalog


def write_catalog(tmp_path, internal_ids, keys=None):
    """A minimal Addressables catalog: one string key per internal id."""
    keys = keys or [f'addr{i}' for i in range(len(internal_ids))]
    kd, bd, ed = bytearray(), bytearray(struct.pack('<i', len(keys))), bytearray()
    for i, k in enumerate(keys):
        kpos = len(kd)
        enc = k.encode()
        kd += bytes([0]) + struct.pack('<i', len(enc)) + enc
        bd += struct.pack('<ii', kpos, 1) + struct.pack('<i', i)
    ed += struct.pack('<i', len(internal_ids))
    for i in range(len(internal_ids)):
        ed += struct.pack('<7i', i, 0, 0, 0, 0, 0, 0)
    cat = {
        'm_KeyDataString': base64.b64encode(bytes(kd)).decode(),
        'm_BucketDataString': base64.b64encode(bytes(bd)).decode(),
        'm_EntryDataString': base64.b64encode(bytes(ed)).decode(),
        'm_InternalIds': internal_ids,
    }
    aa = tmp_path / 'assets' / 'aa'
    aa.mkdir(parents=True)
    (aa / 'catalog.json').write_text(json.dumps(cat), encoding='utf8')
    asset = tmp_path / 'assets' / 'Asset'
    asset.mkdir()
    return asset


def test_stage_catalog_decodes_string_keys(tmp_path):
    write_catalog(tmp_path, ['Assets/A/x.prefab', '{Runtime}/b.bundle'], ['keyA', 'keyB'])
    out = tmp_path / 'out'
    out.mkdir()
    E.stage_catalog(str(tmp_path), str(out))
    got = json.loads((out / 'asset_catalog.json').read_text(encoding='utf8'))
    assert got == {'keyA': 'Assets/A/x.prefab'}  # non-Assets targets are dropped


def test_shipped_bundles_and_bundle_files_filter_to_catalog(tmp_path):
    asset = write_catalog(
        tmp_path, ['{R}/Asset/buff_all_aaa.bundle', '{R}/Asset/audio_x_1.bundle', 'Assets/y']
    )
    for n in ['buff_all_aaa.bundle', 'buff_all_bbb.bundle', 'audio_x_1.bundle']:
        (asset / n).write_bytes(b'')
    assert E.shipped_bundles(str(asset)) == {'buff_all_aaa.bundle', 'audio_x_1.bundle'}
    files = [p.rsplit('\\', 1)[-1].rsplit('/', 1)[-1] for p in E.bundle_files(str(asset))]
    assert files == ['buff_all_aaa.bundle']  # orphan variant and skipped family both gone


def test_shipped_bundles_none_without_catalog(tmp_path):
    (tmp_path / 'Asset').mkdir()
    assert E.shipped_bundles(str(tmp_path / 'Asset')) is None
