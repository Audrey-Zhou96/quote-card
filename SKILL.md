---
name: quote-card
description: 把一句演讲金句或一段语音做成金句卡：静态图 + 卡准音频的竖版短视频。六个模板（editorial / boldblock / split / marker / gradient / photoframe）、三档画幅（3:4 / 1:1 / 9:16）、左上角品牌 logo（浅底配深色 logo / 深底配浅色 logo，自动挑）、关键词荧光笔、配色走 theme 可换品牌、字幕逐句上屏。当用户说"做金句卡""quote card""把这句金句做成卡片""把这段演讲做成字幕视频""卡片模板预览""加个 logo"，或给出一句要发到社交平台的引文时使用。
---

# quote-card

一句金句 → 一份 job 文件 → 静态图 + 卡准音频的竖版视频。

工具全在本地：Playwright 渲染，ffmpeg 合成，faster-whisper 出时间轴。**没有云端 API，没有账号。**

> 完整流程在 [docs/WORKFLOW.md](docs/WORKFLOW.md)，参数和 token 表在 [docs/REFERENCE.md](docs/REFERENCE.md)。
> 这份 skill 不带任何人的品牌色 —— 配色、logo、音频都是"接进来"的一层。

---

## 开始之前

**命令都在本 skill 目录里跑**（`build.py` 跟这些命令是平级的）。
先 `cd` 进来，或者给每条命令加绝对路径 —— 在别的目录直接 `python build.py` 会找不到文件：

```bash
cd ~/.claude/skills/quote-card      # 装在别处就用那个目录的绝对路径
python build.py doctor
```

**先跑一次环境自检**，缺什么当场补，别做到一半才发现：

```bash
python build.py doctor
```

静态图只要浏览器；视频要 ffmpeg + whisper。

## 三个决定先问清楚

只问一次，剩下的一次采集共用：

| | 静态图 | 动态视频 |
|---|---|---|
| 内容来源 | 一句 quote | 一段音频（转成字幕） |
| 额外产物 | PNG | PNG + MP4 |
| 多花的工具 | 无 | whisper、ffmpeg |

再定三样**可复用**的（第二次就该直接读 theme 和 job，不该重问）：
**配色**（theme）、**字体**（`fonts/`）、**尺寸**（`ratio` / `video.ratios`）。

**还要问 logo**（第 3 步）—— 左上角是品牌位，没 logo 的卡跟有 logo 的差一截。
浅底要深色/黑色 logo，深底要白色/浅色 logo。

---

## 流程

### 1 · 挑模板 —— 先铺开，别猜

```bash
python build.py gallery jobs/<job>.json --ratios 1:1        # 静态：六个模板并排
python build.py videogallery jobs/<job>.json --clip 12       # 视频：六个模板各一段 12 秒
```

| 模板 | 长相 | 适合 |
|---|---|---|
| `editorial` | 杂志排版，细线、小标签、破折号署名 | 权威、沉淀、发布会金句 |
| `boldblock` | 整块主色，引文反白出来 | 短句、锐评、态度强的观点 |
| `split` | 上色块引文 / 下素底署名 | 长引文，色块保证对比度 |
| `marker` | 关键词荧光笔 + 手写下划线，右对齐 | 最像"截图会想存"的社交卡 |
| `gradient` | 柔和网格渐变，实色字 | 想要"现代感"但不浮夸 |
| `photoframe` | 上传自己的图 + 遮罩压字 | 人物照、发布会现场图 |

**六个模板就是六个视频模板** —— 模板只负责画，动效在 `runtime.js` 里，
静态和视频共用同一份标记。videogallery 出的是同一段音频的六次渲染，
按播放键同时播放即可对照。

挑中一个 → 把 job 里的 `template` 改成它的名字。

### 2 · 定尺寸

| 画幅 | 像素 | 什么时候用 |
|---|---|---|
| `3:4` | 1080×1440 | **竖版默认**。1080 宽，比 9:16 矮一截，正好放一句话 |
| `1:1` | 1080×1080 | 方卡，图文首图 |
| `9:16` | 1080×1920 | 全屏竖屏。卡片只有一句话时上下都是空的，除非平台要求 |

### 3 · 要 logo（放左上角）

**这一步要主动问，别等用户提。** 一次问全三件事：

1. 有没有 logo（PNG，透明背景，横版字标最省事）
2. 浅底还是深底（theme 和模板定了）→ **浅底配深色 logo，深底配白色 logo**
3. 要不要两版（`photoframe` 压着照片，照片多半偏深，得配一版浅色 logo）

```json
"logo":       "../assets/my-logo-dark.png",    // 浅底用
"logoOnDark": "../assets/my-logo-white.png"    // 深底用
```

工具按模板的地面自动挑（`photoframe` 是深底，别的跟 theme 走）。
logo 占的是 kicker 的位置 —— 给了 logo，kicker 自动让位。

`check` 会读 logo 的像素跟底色比，版本选错会直说。

### 4 · 写 job

复制 `jobs/example.json`，改这几个字段就够：

```json
{
  "name": "example-001",
  "template": "split",
  "theme": "neutral",
  "ratio": ["1:1", "3:4"],
  "quote": "原句",
  "speaker": "Alex Doe, Platform Engineer",
  "title": "Engineering All-Hands 2026",
  "kicker": "KEYNOTE",
  "logo": "../assets/demo/logo-dark.png",
  "showQuoteMark": true,
  "highlight": ["值得高亮的词"]
}
```

- **`showQuoteMark`**：右上角的大引号，默认不开。开了以后右上角的序号（`01`）自动让位 —— 两者互斥。
- **`highlight`**：`marker` 模板的高亮词，写在 job 里，不用改 HTML。
  **必须和文案里的字完全一致**（视频里则要和字幕一致），否则荧光笔不会出现 ——
  `check` 会报命中了几个、哪几个没命中。

### 5 · 视频：先转写，让人过一遍

```bash
python build.py transcribe assets/speech.m4a -o assets/cues.json
python build.py cues jobs/<job>.json
```

**这一步不能省。** whisper 会把口误、重复、口癖一起写进去。

`cues.json` 是普通 JSON，让人直接改：删一行 = 不上屏；把 `text` 清空 = 不上屏；
改字 = 字幕改字；改 `start` / `end` = 字幕跟着挪。

**改完不用重新转写**，直接 `video` 就行。专有名词一定要人工改 ——
whisper 不知道你们的产品怎么写。

### 6 · 渲染前量一遍（别跳过）

```bash
python build.py check jobs/<job>.json     # 静态：这句话排得下吗
python build.py fit   jobs/<job>.json     # 视频：这支片子排得下吗
```

字号自动缩是**不报错**的 —— 缩了只会让字变小，溢出了也不会提示。
这两个命令存在的意义就是在渲染前把这件事说出来。

`check` 报三件事：logo 的颜色配不配底色、荧光笔的词命中几个、字号定在多少。
`fit` 报三件事：实际字号定在多少、最挤的一屏还剩多少空间、满屏之后画面填不填得满。
「余量是负的」= 装不下，砍文案或调小 `keepLines`；「平均只用了 40%」= 画面空，
加大 `quoteScale` 或让 `keepLines` 多留几句。

### 7 · 渲染

```bash
python build.py static jobs/<job>.json     # 只出图
python build.py video  jobs/<job>.json     # 只出视频
python build.py both   jobs/<job>.json     # 两个一起出
```

想先在浏览器里看再决定：`python build.py static jobs/<job>.json --preview`
（多写一个 html，改 token 就能看，不用重跑渲染）。

**产物落在一个 job 一个文件夹**：

```
out/<job 名>/
├── gallery.html        # 静态模板总览
├── videogallery.html   # 视频模板总览
├── stills/             # 静态图
└── videos/             # 视频
```

视频是逐帧截图：1080×1440 / 30fps 约 110ms 一帧，一支 70 秒的片子约 4 分钟。
**先 `fit` 再 `video`** —— 渲完才发现字号不对，得再等 4 分钟。

---

## 视频的字幕怎么排

| 字段 | 意思 |
|---|---|
| `video.accumulate` | `true` = 念过的句子留在屏上变淡；`false` = 一次只显示当前句 |
| `video.keepLines` | 累加模式下同时留在屏上的句数。**3~4 是默认推荐值** |
| `video.density` | `compact` = 行距收紧，句子多时用 |
| `video.start` / `video.end` | 掐头去尾 |
| `video.music` + `musicGain` | 铺一层背景乐，自动压低 |

**不写 `keepLines` = 0** 会把整段话塞进一屏，字号被压到看不清。
**字号整支视频只算一次**（按最挤那一屏定死），所以不要指望某一屏自动变大 ——
要改就改 `tokens.quoteScale`。

---

## 接自己的品牌

配色、字体、图片、logo 是"接进来"的一层，模板和流程一个字都不用动。
详见 [themes/README.md](themes/README.md)：

```bash
cp themes/neutral.json themes/my-brand.json   # 复制一份，改里面的色值
```

字体丢进 `fonts/` 就自动生效。图片写在 `tokens.bgImage`（`photoframe` / `marker` 用），
logo 写在 job 的 `logo` / `logoOnDark`（第 3 步）。

---

## 边界

- 静态图只要浏览器，视频要 ffmpeg + whisper —— 缺件先 `doctor`。
- 转写慢（中文 30 秒音频约 10–15 秒，CPU），**只跑一次**，之后改 `cues.json`。
- 模板多了不用改 `runtime.js`：照抄 `templates/editorial.html`，只写视觉。
  `build.py` 会检查模板里引用的 CSS 变量有没有定义，对不上会警告。
- `photoframe` 没给图会用 `assets/demo-photo.jpg` 顶上 —— 空框是 bug，不是风格。
- 不承诺播放结果 —— 这套工具只管"这条排得下、看得清"。
