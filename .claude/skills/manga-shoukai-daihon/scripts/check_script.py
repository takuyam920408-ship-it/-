#!/usr/bin/env python3
"""漫画紹介ショート台本（.txt）の数値と構成をチェックする。

使い方: python3 check_script.py 台本.txt
要修正が1件でもあれば終了コード1を返す。
"""
import re
import sys

CHARS_PER_SEC = 7  # 伸びているチャンネルの話す速さ（1秒あたりの文字数）
NARRATOR = {"ナレ", "ナレーション"}
TSUKKOMI = "ツッコミ"
PUNCT = re.compile(r"[\s　、。，．,.！？!?…‥「」『』（）()〜~・:：]")
CTA = re.compile(r"続き|概要欄|説明欄|長押し")


def norm(s):
    return PUNCT.sub("", s)


def split_sections(text):
    """【見出し】ごとに本文を分ける。見出しと同じ行の文字は本文の1行目にする。"""
    sections, cur = {}, None
    for line in text.splitlines():
        m = re.match(r"^【(.+?)】(.*)$", line.strip())
        if m and m.group(1) in {"型", "タイトル", "タイトル案", "台本", "画面・音", "ハッシュタグ", "概要欄"}:
            cur = m.group(1)
            sections[cur] = [m.group(2).strip()] if m.group(2).strip() else []
        elif cur:
            sections[cur].append(line)
    return {k: "\n".join(v).strip() for k, v in sections.items()}


def parse_blocks(script):
    """［話者］ごとにセリフをまとめる。"""
    blocks = []
    for line in script.splitlines():
        line = line.strip()
        if not line:
            continue
        m = re.match(r"^［(.+?)］(.*)$", line)
        if m:
            blocks.append([m.group(1).split("（")[0].strip(), m.group(2).strip()])
        elif blocks:
            blocks[-1][1] += line
        else:
            blocks.append(["?", line])
    return blocks


def main(path):
    text = open(path, encoding="utf-8").read()
    sec = split_sections(text)
    results = []  # (判定, 項目, 詳細)  判定は OK / 要修正 / 確認

    def add(ok, item, detail, soft=False):
        results.append(("OK" if ok else ("確認" if soft else "要修正"), item, detail))

    kind = sec.get("型", "")
    btype = kind.startswith("B") or ("台本" not in sec and "タイトル案" in sec)

    if not btype:
        blocks = parse_blocks(sec.get("台本", ""))
        if not blocks:
            add(False, "台本", "【台本】が見つからない")
        else:
            total = sum(len(norm(t)) for _, t in blocks)
            add(350 <= total <= 420, "読み上げ文字数", f"{total}字（目安350〜420字）→ 約{total / CHARS_PER_SEC:.0f}秒")

            before, first = 0, None
            for sp, t in blocks:
                if sp not in NARRATOR and TSUKKOMI not in sp:
                    first = before
                    break
                before += len(norm(t))
            if first is None:
                add(False, "最初のセリフ", "キャラのセリフがない")
            else:
                add(first / CHARS_PER_SEC <= 5, "最初のセリフ", f"約{first / CHARS_PER_SEC:.1f}秒目（目安5秒以内）")

            n_tsk = sum(1 for sp, _ in blocks if TSUKKOMI in sp)
            add(2 <= n_tsk <= 4, "ツッコミ回数", f"{n_tsk}回（目安2〜4回）")

            title = norm(sec.get("タイトル", "").splitlines()[0] if sec.get("タイトル") else "")
            hook = norm(blocks[0][1])
            same = bool(title) and (title in hook or hook in title)
            add(same, "フック", "タイトルを冒頭で読み上げている" if same
                else "冒頭とタイトルが違う（漫画ムラ型で意図的なら問題なし）", soft=True)

            has_cta = bool(CTA.search(blocks[-1][1]))
            if "ぶつ切り" in kind:
                add(not has_cta, "締め", "ぶつ切り締め指定 → 最後にCTAがない" if not has_cta
                    else "ぶつ切り締め指定なのに最後にCTAがある")
            elif "CTA" in kind:
                add(has_cta, "締め", "最後にCTAがある" if has_cta else "CTA締め指定なのに最後にCTAがない")
            else:
                add(True, "締め", "CTAあり" if has_cta else "CTAなし（ぶつ切り）", soft=not has_cta)

            commas = sum(t.count("、") for _, t in blocks)
            add(commas <= 3, "読点", f"{commas}個（区切りは改行か半角スペースで）", soft=True)
    else:
        titles = [re.sub(r"^\s*\d+[.．、)]\s*", "", l).strip()
                  for l in sec.get("タイトル案", "").splitlines() if re.match(r"^\s*\d", l)]
        add(len(titles) >= 3, "タイトル案", f"{len(titles)}案（目安3案）")
        long = [t for t in titles if len(norm(t)) > 20]
        add(not long, "タイトル案の長さ", "すべて20字以内" if not long else f"20字超: {' / '.join(long)}", soft=True)
        add("画面・音" in sec, "画面・音", "【画面・音】あり" if "画面・音" in sec else "【画面・音】がない")

    tags = sec.get("ハッシュタグ", "")
    add("#漫画" in tags, "ハッシュタグ", tags.replace("\n", " ") or "なし")

    desc = sec.get("概要欄", "")
    lines = [l for l in desc.splitlines() if l.strip()]
    add(bool(lines) and lines[0].strip().startswith("http"), "概要欄の1行目", lines[0].strip() if lines else "概要欄がない")
    add("長押し" in desc or "タップ" in desc, "開き方の案内", "あり" if ("長押し" in desc or "タップ" in desc) else "URLの開き方が書かれていない")
    intro = re.search(r"【作品紹介】|＜どんな作品？＞|📝作品概要|【説明】|【作品詳細】", desc)
    add(bool(intro), "作品紹介", "あり" if intro else "作品紹介の段落がない")
    add("アフィリエイト" in desc or "PR" in desc or "広告" in desc, "広告表記",
        "あり" if ("アフィリエイト" in desc or "広告" in desc) else "アフィリエイトなら「※アフィリエイト広告を利用しています」を入れる", soft=True)

    print(f"■ {path}（{'B型' if btype else 'A型'}）")
    for r, item, detail in results:
        print(f"  [{r}] {item}: {detail}")
    ng = sum(1 for r, _, _ in results if r == "要修正")
    print(f"→ 要修正 {ng}件" if ng else "→ すべてOK（[確認] の項目は目で見て判断）")
    return 1 if ng else 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
