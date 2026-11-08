// 1本ぶんの設計図（spec.json）の形

export type Telop = {
  text: string; // 改行は \n（1行11字まで、2行まで）
  color?: 'blue' | 'green' | 'red' | 'orange' | 'purple' | 'magenta';
  at?: number; // カットが始まってから何秒後に出すか（上テロップは省略で0秒）
};

export type Photo = {
  src: string; // public/ からのパス
  label?: string; // 出典ラベル（例：出典：本人のX）
  tag?: string; // 2枚比較のラベル（例：10年前／今）
  focusY?: number; // 枠いっぱいに切り取るとき（冒頭画面・2枚比較）、縦のどこを中心にするか（0＝上の端〜1＝下の端。既定0.3）
};

export type TitleCut = {
  type: 'title';
  pattern: 'A' | 'B' | 'C'; // A＝縦に昔→今、B＝横に昔→今、C＝1枚まるごとモザイク
  dur: number;
  title: string; // 冒頭の文（\n で改行、3行まで）
  before?: Photo; // 昔の写真（A・B）
  after: Photo; // 今の写真（モザイクをかける）。肩から上に切り取った画像を使う
  mosaic?: number; // モザイクのマスの大きさ（px、40〜60）
  voice?: string;
};

export type BodyCut = {
  type: 'single' | 'reveal' | 'wide';
  dur: number;
  image: Photo;
  top: Telop;
  bottom: Telop[]; // reveal だけ2つまで
  mosaic?: number; // single だけ：公開の直前の溜めで、今の写真をモザイクのまま見せるとき（マスの大きさpx）
  voice?: string;
  se?: string;
};

export type CompareCut = {
  type: 'compare';
  dur: number;
  images: [Photo, Photo]; // 上（左）＝昔、下（右）＝今
  layout?: 'vertical' | 'side'; // vertical＝上下に並べる（既定。横長の写真向き）／side＝左右に並べる（縦長の写真向き）
  top: Telop;
  bottom: Telop[];
  voice?: string;
};

export type Cut = TitleCut | BodyCut | CompareCut;

export type Sfx = {
  title?: string | null; // 冒頭の画面が出るときの音（既定 se/don.wav）
  telop?: string | null; // テロップが出るたびの音（既定 se/pon.wav）
  cut?: string | null; // カットが切り替わるたびの音（既定なし。例 se/shu.wav）
  volume?: number; // 効果音の大きさ（既定 0.5）。公開の se は 1.6倍で鳴らす
};

export type Spec = {
  id: string;
  cuts: Cut[];
  yomi?: Record<string, string>; // 読み上げの読みの直し（scripts/koe.py が使う）
  sfx?: Sfx;
  creditLabels?: boolean; // 画面に「出典：〇〇」のラベルを出すか（既定 false。出典は概要欄に書く。2026-11-08 ユーザーが決定）
  bgm?: string;
  bgmVolume?: number;
};
