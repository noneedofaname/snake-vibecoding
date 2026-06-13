import urllib.request
import os

images = {
    "tomori": "https://storage.moegirl.org.cn/moegirl/commons/3/3c/Gbp_character_kv_edited_v2_tomori.webp",
    "anon": "https://storage.moegirl.org.cn/moegirl/commons/6/68/Gbp_character_kv_edited_anon.webp",
    "rana": "https://storage.moegirl.org.cn/moegirl/commons/5/5c/Gbp_character_kv_edited_rana.webp",
    "soyo": "https://storage.moegirl.org.cn/moegirl/commons/2/26/Gbp_character_kv_edited_v3_soyo.webp",
    "taki": "https://storage.moegirl.org.cn/moegirl/commons/b/be/Gbp_character_kv_edited_v2_taki.webp",
    "uika": "https://storage.moegirl.org.cn/moegirl/commons/0/0d/ON_character_kv_Uika.webp",
    "mutsumi": "https://storage.moegirl.org.cn/moegirl/commons/0/0d/ON_character_kv_Mutsumi.webp",
    "umiri": "https://storage.moegirl.org.cn/moegirl/commons/3/33/ON_character_kv_Umiri.webp",
    "nyamu": "https://storage.moegirl.org.cn/moegirl/commons/f/f3/ON_character_kv_Nyamu.webp",
    "sakiko": "https://storage.moegirl.org.cn/moegirl/commons/3/31/ON_character_kv_Sakiko.webp",
}

output_dir = os.path.dirname(os.path.abspath(__file__))

for name, url in images.items():
    out_path = os.path.join(output_dir, f"{name}.webp")
    if os.path.exists(out_path):
        print(f"✓ {name}.webp 已存在，跳过")
        continue
    print(f"↓ 下载 {name}...", end=" ", flush=True)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        data = urllib.request.urlopen(req, timeout=30).read()
        with open(out_path, "wb") as f:
            f.write(data)
        print(f"OK ({len(data)} bytes)")
    except Exception as e:
        print(f"FAIL: {e}")

print("\n全部完成!")
