# Codex：背景描画補正・統合QA

## 実施範囲

- C-01：L3の矩形拡張と既存物体の位置保持を実装。画像外の欠損補完は行っていない。
- C-02：L2の背後に、暗い接続用背景を初期化時に生成する処理を実装。
- C-03：組立済みv3を別プロファイルで統合検証済み。全体案は不採用、L3右側だけは部分候補として保留。
- C-04：既存139件＋新規13件＝**152件成功**。描画前後の物理トレース一致も検証。

正式素材は引き続きdraft_v1。finish_v2・v3の正式採用はしていない。
今回の実装はユーザーが指示した描画設定・矩形の補正であり、素材の切り替えではない。
Claudeの作業領域candidates_v3とは編集ファイルを分離している。

## 変更ファイル

| ファイル | 内容 |
| --- | --- |
| `game/stages/background.py` | オプションのanchor_src、描画原点、拡張後のカリング、ground_connector設定・初期生成・描画順 |
| `game/stages/stage_1.json` | background内のruin_right矩形・anchor_src・ground_connectorのみ変更 |
| `game/tests/test_background_corrections.py` | 新規13テスト |
| 本ディレクトリ | 補正前設定の記録、QAスクリプト、比較画像、検証記録 |

## C-01：L3の矩形と位置保持

`ruin_right`は `[1330,640,342,301]` から `[1240,640,432,301]` に拡張した。
左へ90原寸px、内部描画では52pxを追加し、左で切れていた枯草を多く取り込む。
上端・下端・画像右端は変えない。画像全体に存在しない岩の輪郭は、この操作では復元できない。

`anchor_src: [1330,640,342,301]`により、旧矩形を配置・拡大縮小の基準として保持する。
従来の岩部分は従来どおりの196×173pxでサンプリングし、拡張部分と原点だけを追加する。
単に拡張画像を中央揃えし直す方法と異なり、JSONのplacement.xやbottomは動かさない。

テストで確認した内容：

- 旧矩形に対応する196×173pxのRGBAが、補正前の描画画像と完全一致する。
- 負・小数・大きなカメラ位置、周期オフセットでも、旧物体の表示座標が変わらない。
- 追加した草だけが画面に掛かる場合もカリングしすぎない。
- 範囲外・無効なanchor_srcを設定エラーとして拒否する。

矩形拡大は自然な物体分割の完成を保証するものではない。
新しい左辺にも地面近くの草が残るので、ピット付近を含む実画面での確認が必要。
`ruin_left`の画像左端、`ruin_right`の画像右端で欠けている部分はClaudeのv3候補待ち。
現在の端のぼかし設定も維持している。

## C-02：地面際の接続用背景

JSONの`ground_connector`を追加：

```json
{
  "before_layer": "L1_far_castle",
  "top": 360,
  "height": 58,
  "color": [38, 23, 29],
  "max_alpha": 255
}
```

描画順はL0 → 接続用背景 → L1 → L2 → L3 → 既存の下部暗化 → 地形 → 敵・主人公・攻撃・照準等。
接続用背景はy360〜418で暗い土色へ移り、そこから下を覆う。
L1より前に置くため、建築物そのものを上から黒く覆う処理ではない。
半透明領域の背後の色は変わるが、空の上部・大聖堂・橋・塔の座標や形、L2の上下位置は変えない。

オプションを省略すれば従来の描画になる。未定義レイヤーやL0の前へ置く設定は拒否する。
生成は初期化時のみで、毎フレームの画像読み込み・拡大縮小は追加していない。
既存の画像欠落／破損時フォールバックとキャッシュを維持する。

## 比較画像

- cam0：[補正前](before_cam0.png)／[補正後](corrected_cam0.png)
- cam600：[補正前](before_cam600.png)／[補正後](corrected_cam600.png)
- cam1200：[補正前](before_cam1200.png)／[補正後](corrected_cam1200.png)
- cam2240：[補正前](before_cam2240.png)／[補正後](corrected_cam2240.png)
- [ruin_right：上段が旧矩形、下段が拡張後](ruin_right_before_top_corrected_bottom.png)
- `*_wrap-1.png`／`*_wrap+0.png`／`*_wrap+1.png`：L1/L2の周期境界前後。

統合画像は960×540、壁はcamera+140、主人公はcamera+300へQA用に置いている。
壁より前にいる画面内の敵へ輪郭と照準を表示し、HUDも重ねている。
静止画では赤い帯の低減と、主人公・敵・紫の照準・赤い壁の表示を確認した。
これは実際のOSマウス入力、動的プレイの視認性、DPI、実機60FPSの合格を意味しない。

## C-03：正式採用しない候補プロファイル

`render_integration.py`は現在の設定を変更せず、メモリ上の別プロファイルで候補を読み込む。
`qa_profiles.json`に読み込んだ候補と保護領域検証を記録する。

```powershell
# 現行素材：補正前後を比較
python -B game/assets/backgrounds/twilight_ruins/qa_integration_codex/render_integration.py

# Claudeの組立済み候補を、実際のパスに置き換えて指定する
python -B game/assets/backgrounds/twilight_ruins/qa_integration_codex/render_integration.py `
  --candidate L1=C:/path/to/L1_candidate.png `
  --candidate L2=C:/path/to/L2_candidate.png `
  --candidate L3=C:/path/to/L3_candidate.png
```

prep_manifestに宣言されたサイズ・元画像オフセット・原寸RGBAの完全一致を検査してから表示する。
大きくなったキャンバス全体を960px幅へ縮めず、元の1672px→960pxの基準を保ち、追加領域を別に描く。
L1/L2は候補用の新周期でseamなし、L3は元の物体基準に外側の補完部分を追加するQA専用アダプター。
L3では現行の端のぼかしを基準部分に保持しているため、補完との接続を含めた設定調整の要否は別途判断する。
このQA専用アダプターは製品レンダラーの候補対応完了を意味しない。

候補がまだない状態は`waiting for assembled v3 candidates`として記録し、成功や正式採用とは扱わない。
組立済み候補を検証する場合は、Claudeの組立・保護検証が終わったものを指定する。

### v3統合検証結果

Claudeが組み立てたL1/L2/L3を読み込み、サイズ・原画オフセットと、元1672×941領域のRGBA完全一致をこちらでも検証した。
3枚とも一致。L1は1992×941、L2は2056×941、L3は1896×941で元画像はx96にある。
原画部分の縮尺を維持し、L1/L2のQA周期は1144／1180px。これは正式設定の864pxとは異なる。

| 対象 | 統合画像での確認 | 判定 |
| --- | --- | --- |
| L1 | 大聖堂の元画素は維持。しかし追加領域との境界に明るさ・地形の切れ目がある | 不採用 |
| L2 | 二重化はないが、新しいアーチの尖った輪郭と地面の段差・切断が目立つ | 不採用 |
| L3左 | 元の岩と補完部分で形がつながらない。既存のぼかしも統合時の検討要素として残る | 不採用 |
| L3右 | 原画座標の接続拡大では自然な石の端に見える。現行のL1/L2との統合画像にも表示できた | 部分候補。未承認・未反映 |
| 地面際 | 接続用背景により赤い空の露出は低減。ただしv3の地面の段差自体は隠しきれない | 素材側の修正が必要 |
| 主人公・敵・照準・壁 | 比較静止画で読み取れる。新しいアーチが背景の情報量を増やしており、人の動的評価は別途必要 | 実プレイ合格とは扱わない |

候補全体の記録は[qa_profiles_candidate_unapproved.json](qa_profiles_candidate_unapproved.json)。
近景右だけを読み込む独立プロファイルも検証した：

```powershell
python -B game/assets/backgrounds/twilight_ruins/qa_integration_codex/render_integration.py `
  --candidate L3=game/assets/backgrounds/twilight_ruins/candidates_v3/candidates/L3_candidate.png `
  --l3-right-only
```

- [全候補・cam1200](candidate_unapproved_cam1200.png)／[cam2240](candidate_unapproved_cam2240.png)
- [全候補・L1周期境界](candidate_unapproved_L1_far_castle_wrap+0.png)
- [全候補・L2周期境界](candidate_unapproved_L2_mid_invasion_wrap+0.png)
- [L3右のみ・cam1200](candidate_L3_right_only_unapproved_cam1200.png)／[cam2240](candidate_L3_right_only_unapproved_cam2240.png)
- [右のみプロファイルの記録](qa_profiles_candidate_L3_right_only_unapproved.json)
- 素材単体の2/3タイル比較・保護マスク・差分は[Claudeのv3報告](../candidates_v3/README.md)を参照。

どちらのプロファイルもQA専用。正式JSON・draft_v1の参照先は変更していない。
L3右の採用には、ユーザーの確認に加え、拡張画像の基準寸法・配置・ぼかしを製品側でどう扱うかの判断が必要。

## C-04：回帰テスト

```powershell
python -B -m unittest discover -s game/tests -v
```

152件成功。新規13件で、旧物体画素／座標保持、拡張後のカリング、設定エラー、旧設定互換、
L0〜L2画素と位置の不変、接続用背景の描画順と上部画素不変、キャッシュ区別、素材欠落フォールバック、
補正前後のゲームプレイトレース一致を検証した。既存の周期境界・毎フレームの読込／拡大縮小禁止テストも成功。
破損PNGのテストによりlibpng診断が出るが、テストは成功している。

## 未解決・採用判定

- L1/L2のcrossfade二重化は今回直していない。
- 原画の外側で欠けた岩、右スプライト内の草の最終的な自然さは素材と実プレイでの確認が必要。
- v3素材の統合QAは実施済み。全体候補は不採用、L3右だけ部分候補。finish_v2は引き続き不採用。
- DPI100/125/150%、実ウィンドウのリサイズ、実機60FPS、初見の誤認しにくさは未検証。
- **v3全体の正式採用は不可**。L3右の部分採用も未承認で、正式素材には反映していない。
- 現在のdraft_v1に対する描画補正は実装・自動検証済み。見た目の最終判断は比較画像で確認する。
