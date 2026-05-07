"""
DBF 编码诊断工具
用法：python detect_encoding.py 你的文件.dbf
"""
import sys
import struct


def read_dbf_strings(path, encoding, max_rows=3):
    """直接读取 DBF 文件原始字节，用指定编码解码"""
    results = []
    try:
        with open(path, "rb") as f:
            # DBF 文件头：32 字节，第 8-11 字节是记录数
            header = f.read(32)
            num_records = struct.unpack_from("<I", header, 4)[0]
            header_size = struct.unpack_from("<H", header, 8)[0]
            record_size = struct.unpack_from("<H", header, 10)[0]

            # 读字段描述（每个字段 32 字节，\r 结束）
            fields = []
            while True:
                field_desc = f.read(32)
                if field_desc[0] == 0x0D:
                    break
                name = field_desc[:11].rstrip(b"\x00").decode("ascii", errors="replace")
                ftype = chr(field_desc[11])
                flen = field_desc[16]
                fields.append((name, ftype, flen))

            # 跳到数据区
            f.seek(header_size)
            rows_to_read = min(max_rows, num_records)
            for _ in range(rows_to_read):
                raw = f.read(record_size)
                if not raw or raw[0] == 0x1A:
                    break
                row = {}
                offset = 1  # 第一个字节是删除标记
                for name, ftype, flen in fields:
                    raw_val = raw[offset: offset + flen]
                    if ftype == "C":  # 字符型字段
                        try:
                            row[name] = raw_val.rstrip(b"\x00 ").decode(encoding)
                        except Exception:
                            row[name] = f"[解码失败]"
                    offset += flen
                results.append(row)
    except Exception as e:
        return f"读取失败：{e}"
    return results


def main():
    if len(sys.argv) < 2:
        print("用法：python detect_encoding.py 你的文件.dbf")
        return

    dbf_path = sys.argv[1]
    encodings = ["gbk", "gb2312", "gb18030", "utf-8", "utf-8-sig", "big5", "latin-1"]

    print(f"\n文件：{dbf_path}")
    print("=" * 60)
    print("逐一尝试各种编码，找到中文显示正常的那个即为正确编码：")
    print("=" * 60)

    for enc in encodings:
        result = read_dbf_strings(dbf_path, enc)
        print(f"\n【{enc.upper()}】")
        if isinstance(result, str):
            print(f"  {result}")
        elif not result:
            print("  （无数据）")
        else:
            for i, row in enumerate(result):
                print(f"  第{i+1}行：{row}")


if __name__ == "__main__":
    main()
