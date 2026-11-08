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
  voice?: string;
  se?: string;
};

export type CompareCut = {
  type: 'compare';
  dur: number;
  images: [Photo, Photo]; // 上＝昔、下＝今
  top: Telop;
  bottom: Telop[];
  voice?: string;
};

export type Cut = TitleCut | BodyCut | CompareCut;

export type Spec = {
  id: string;
  cuts: Cut[];
  bgm?: string;
  bgmVolume?: number;
};
