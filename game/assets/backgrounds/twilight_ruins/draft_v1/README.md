# 黄昏の廃王国：背景レイヤー素材案 v1

承認された「夕焼けの廃王国＋機械侵食を強めた案」を参照し、内蔵image_genで生成。
コードへの組み込みは未実施。既存マップ・当たり判定・移動・背景レンダラーは変更していない。

| PNG | 役割 | サイズ | 透過 |
| --- | --- | --- | --- |
| 01_sky.png | 夕焼け・雲・太陽 | 1672×941 | 全体不透明 |
| 02_far_castle.png | 遠景の廃城・丘陵 | 1672×941 | アルファ0〜255 |
| 03_mid_invasion.png | 中景の侵食都市・収穫構造 | 1672×941 | アルファ0〜255 |
| 04_near_debris.png | 手前の瓦礫・枯草 | 1672×941 | アルファ0〜255 |

空→遠景→中景→近景の順に重ねる想定。PNGの寸法とアルファ情報はpygameで読み取り確認済み。
これらは素材案であり、まだゲーム用の完成アセットではない。
960×540への配置調整、重ね合わせ時の濃度・境界色、スクロール中の隙間、左右の継ぎ目、
プレイヤー・敵・地形との視認性は未検証。左右のシームレス接続は保証しない。
近景は装飾であり、PNG内の石や瓦礫に当たり判定を付ける意図はない。

## 生成プロンプト

参照画像は各呼び出しで直前の承認コンセプト1枚を指定。下記の共通文＋各レイヤー文で生成。
空は `transparent_background=false`、他は `true`。

### 共通文

Use the most recent concept image as the sole visual reference: the approved warm sunset ruined Gothic kingdom under active alien assimilation. Create an individual parallax BACKGROUND LAYER asset, not a whole scene and not a labeled diagram. Wide landscape 16:9 canvas, match the reference composition, hand-painted style and scale, horizon at about 65 percent height, eventual gameplay ground at about 78 percent height. Keep the warm burnt orange, gold, dusty burgundy and plum palette, with restrained teal only in alien machinery. Camera is strictly side-on for a 2D horizontal platformer. No characters, enemies, UI, lettering, watermark, no white/black backing sheet, no checkerboard pattern. This is one layer of a four-layer stack; avoid duplicating subjects assigned to the other layers.

### 01_sky

LAYER 1 SKY ONLY. Paint a fully opaque atmospheric sky covering the entire canvas. Rich plum and dark burgundy storm clouds above, burnt orange sunset opening at left-center, low golden sun centered at x35 percent y62 percent, smoky warm haze near the horizon transitioning to dark dusty reddish haze at the bottom. Painterly cloud forms and soft subtle ash haze, clear broad values. Remove all architecture, alien structures, foreground trees, terrain, grass and stone. Only sky, clouds and sun. Match the approved image's lighting and mood. Seamlessly calm left and right edges suitable for a long horizontal scrolling sky.

### 02_far_castle

LAYER 2 FAR DISTANT RUINED KINGDOM ONLY, genuinely transparent background. A monumental ruined medieval Gothic cathedral occupies the upper-right skyline, old stone royal ramparts and progressively smaller broken towers trail toward the left. Buildings stand on softly painted distant hill silhouettes mainly between y30 and y75 percent; central cathedral highest tower reaches about y12 percent. The cathedral is mostly old stone, not heavily mechanized. Hazy dusty burgundy silhouettes, sunlit warm muted edges facing left, restrained painterly details and low contrast suitable for the distant layer. Leave the sky and upper negative space completely transparent, leave the lower foreground area transparent; the hills end in soft translucent haze rather than a hard rectangle. NO sun, clouds, foreground arches, grasses, close masonry or large alien harvesting lattice. Only far castle and distant hillside ruins.

### 03_mid_invasion

LAYER 3 MIDDLE DISTANCE ALIEN-ASSIMILATED RUINS ONLY, genuinely transparent background. A panoramic band of broken medieval city walls, old bridges and smaller Gothic towers among low ruined hills. Obsidian biomechanical ribs grow through parts of the walls and wrap several towers, thin restrained teal energy veins. At far left, an alien harvesting lattice consumes buildings into suspended masonry fragments and faint energy strands; the city is actively being converted to energy. Most of this layer occupies y38 to y78 percent, few slender structures rise to y25 percent; keep the center somewhat open. Medium contrast dusty copper, muted burgundy and warm charcoal with translucent atmospheric haze. Absolutely NO dominant giant cathedral (it belongs to the far layer), no sky, sun, clouds, near foreground arch frames, grass, continuous ground/platform. Leave all empty areas truly transparent. Layered architectural band with transparent sky and lower area.

### 04_near_debris

LAYER 4 NEAR FOREGROUND DRESSING ONLY, genuinely transparent background. Sparse dark charcoal and warm brown broken stones, small rubble piles, dried straw grasses, a few thin bare twigs at the extreme left and right, concentrated along the BOTTOM 15 percent of the canvas. Some isolated masonry fragments and tiny clumps of grass at lower corners reach to y76 percent but do not obstruct the middle gameplay area. Rich painterly worn stone texture, very subtle warm sunset rim light from left, no teal lights. Most of the canvas (upper 75 percent and central open area) must be fully transparent. NO skyline, hills, cathedral, alien towers, sun, sky, distant city, large arches, tall walls, flat continuous platform or solid ground rectangle. This is sparse foreground decoration laid over game terrain, not collision geometry. Keep horizontal outer edges sparse for scrolling.
