"""アダプタ・スコアリング・文面生成をつなぐデータ構造。"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ImageCandidate:
    """ページから見つかった画像1枚と、その画像に付随していたテキスト。

    AI を使わないので「画像の中身」は分からない。文面の手がかりは
    alt / caption / nearby_heading に入っているテキストが全て。
    """

    url: str
    source: str = "img"  # og | twitter | img | srcset | link
    alt: str = ""
    caption: str = ""
    nearby_heading: str = ""
    declared_width: int | None = None
    declared_height: int | None = None
    width: int | None = None
    height: int | None = None
    content_type: str = ""
    cache_id: str = ""
    score: float = 0.0
    reasons: list[str] = field(default_factory=list)

    @property
    def area(self) -> int:
        w = self.width or self.declared_width or 0
        h = self.height or self.declared_height or 0
        return w * h

    @property
    def context_text(self) -> str:
        return " ".join(x for x in (self.alt, self.caption, self.nearby_heading) if x)


@dataclass
class PageMeta:
    """ページ単位のメタ情報。文面生成のスロット抽出元になる。"""

    url: str
    final_url: str = ""
    title: str = ""
    og_title: str = ""
    og_description: str = ""
    site_name: str = ""
    published_at: str = ""
    path_segments: list[str] = field(default_factory=list)

    @property
    def context_text(self) -> str:
        return " ".join(
            x for x in (self.og_title, self.title, self.og_description, self.site_name) if x
        )


@dataclass
class Slots:
    """テンプレートに差し込む値。空欄があるテンプレートは使わない。"""

    work: str | None = None
    work_tag: str | None = None
    work_id: str | None = None
    episode: str | None = None
    characters: list[str] = field(default_factory=list)
    title: str = ""
    source_url: str = ""
    video_url: str = ""
    site_name: str = ""

    def as_dict(self) -> dict[str, str]:
        return {
            "作品名": self.work or "",
            "作品名タグ": self.work_tag or (self.work or ""),
            "話数": self.episode or "",
            "キャラ名": self.characters[0] if self.characters else "",
            "タイトル": self.title,
            "元記事URL": self.source_url,
            "動画URL": self.video_url,
            "サイト名": self.site_name,
        }

    def filled_keys(self) -> set[str]:
        return {k for k, v in self.as_dict().items() if v}


@dataclass
class Draft:
    """生成された投稿文の1案。"""

    template_id: str
    template_type: str
    text: str
    phrase: str = ""
    missing: list[str] = field(default_factory=list)
