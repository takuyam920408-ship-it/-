// 答え合わせ速報の画面デザイン（スキルの references/edit-design.md と同じ値）
export const W = 1080;
export const H = 1920;
export const FPS = 30;

export const BG_DARK = '#FF8A1F';
export const BG_LIGHT = '#FFC48A';
// 背景の放射線は、ずっとゆっくり回す（ベンチマーク①の1位動画を測ると、左回りに1秒約13度。2026-11-08）
export const BG_ROTATE_DEG_PER_SEC = -12; // マイナス＝左回り。1周30秒
// 冒頭画面の写真は、カットのあいだに少しずつ大きくする（ベンチマーク①の冒頭画面と同じ）
export const TITLE_ZOOM = 0.05; // カットの終わりで1.05倍
export const INK = '#141414';
export const MAGENTA = '#E4007F';
export const ARROW_RED = '#E51A1A';

export const TEXT_COLORS: Record<string, string> = {
  blue: '#1A1AC8', // ふつうの説明
  green: '#0B7A2E', // 日付・年齢・肩書き
  red: '#C8102E', // 強調・数字・決め
  orange: '#D9480F', // 強調の2色目
  purple: '#7708AF', // ツッコミ・反応
  magenta: MAGENTA, // タイトル
};

export const FONT = "'M PLUS Rounded 1c', sans-serif";

// 置く範囲
export const TOP_TELOP_Y = 97;
export const PHOTO = { x: 55, y: 386, w: 970, h: 1147 };
export const BOTTOM_EDGE = 1552; // 下テロップの下の端
