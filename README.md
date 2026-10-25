# quote-card

演讲金句卡生成器。一份 job 文件 → 静态图 + 卡准音频的竖版短视频。

**全本地跑** —— Playwright 渲染、ffmpeg 合成、faster-whisper 出时间轴。
没有云端 API，没有账号，没有配额。

> 完整制作流程（从"要静态还是动态"到"归档"）在 [docs/WORKFLOW.md](docs/WORKFLOW.md)，
> 流程图在 [docs/flow.png](docs/flow.png)。
>
> 配色、字体、logo、图片都是"接进来"的一层 —— **这套代码本身不带任何人的品牌色**。

---

## 拿到代码

```bash
git clone https://github.com/Audrey-Zhou96/quote-card.git
cd quote-card
```

## 先装依赖

需要 **Python 3.9+**，然后：

```bash
pip install -r requirements.txt
playwright install chromium      # 第一次要下 Chromium，约 150MB
```

`ffmpeg` 不是 pip 包，是系统里的一个程序，得单独装：

| 系统 | 命令 |
|---|---|
| Windows | `winget install Gyan.FFmpeg`，或从 [ffmpeg.org/download.html](https://ffmpeg.org/download.html) 下 |
| macOS | `brew install ffmpeg` |
| Linux | `sudo apt install ffmpeg` |

装完先自检，**缺什么会一行一行指出来**：

```bash
python build.py doctor
```

```
quote-card doctor

  ok        ffmpeg   /usr/local/bin/ffmpeg
  ok        ffprobe  /usr/local/bin/ffprobe
  ok        playwright chromium 151.0.7922.34   (needed for every render)
  ok        faster-whisper 1.2.1   (needed for video)
  ok        pillow 12.3.0   (needed for every render)
  WARN      fonts/ has no font file   (themes fall back to the next family in the stack)

  static cards need only the browser. videos need ffmpeg + whisper.
```

**各装各的用处**：

| 装它是为了 | 少了会怎样 |
|---|---|
| Playwright + Chromium | 渲不了任何东西 —— 每个像素都是浏览器截出来的 |
| Pillow | 2× 超采样压不回原尺寸，边缘发毛；logo 的颜色检查也读不了像素 |
| ffmpeg | 渲得了图，渲不了视频 |
| faster-whisper | 同上。没有它就没有字幕时间轴，只能手写 `cues.json` |

> `faster-whisper` 第一次跑会下模型（几百 MB），下完就完全离线了。
> 字体缺不缺不影响 —— theme 会退到字体栈的下一个。想用自己的字体就丢进 `fonts/`。

**上游项目**（查文档、报 bug 用这些）：

| | 干什么的 |
|---|---|
| [Playwright](https://github.com/microsoft/playwright) · [Chromium](https://github.com/chromium/chromium) | 浏览器渲染 |
| [Pillow](https://github.com/python-pillow/Pillow) | 缩图、读像素 |
| [faster-whisper](https://github.com/SYSTRAN/faster-whisper) | 音频 → 带时间轴的字幕 |
| [FFmpeg](https://github.com/FFmpeg/FFmpeg) · [下载页](https://ffmpeg.org/download.html) | 合成 mp4 |

---

## 命令

```bash
# 0) 环境自检（缺什么现在补，别做到一半才发现）
python build.py doctor

# 1) 音频 -> 带时间轴的字幕（只跑一次，之后复用）
python build.py transcribe assets/speech.m4a -o assets/cues.json

# 2) 静态图
python build.py static jobs/example.json

# 3) 短视频，字幕跟着语音逐句上屏
python build.py video jobs/example.json

# 两个一起出
python build.py both jobs/example.json

# 不知道选哪个模板？同一段文案一次渲染全部模板
python build.py demo jobs/example.json

# 六个模板铺开成一张可浏览的对照页
python build.py gallery jobs/example.json --ratios 1:1

# 六个模板各渲一段 12 秒，同源同时播放，一页看完哪个适合做视频
python build.py videogallery jobs/example.json --clip 12

# 这句话排得下吗？会不会被自动缩字号？logo 颜色对不对？荧光笔命中了吗？
python build.py check jobs/example.json

# 这支视频排得下吗？字号会定在多少？画面填得满吗？
python build.py fit jobs/example.json

# 把转写稿打出来，好让人先校对一遍
python build.py cues jobs/example.json

# 顺手出一份能直接用浏览器打开的 HTML（改 token 看效果，不用重跑渲染）
python build.py static jobs/example.json --preview
```

`transcribe` 之后 `cues.json` 就是一份普通 JSON，可以直接手改 —— 改完不用重新转写，
`video` 会按你改过的时间轴渲染。**清空某一条的 `text` 就是让这条字幕不上屏。**

---

## 产物放在哪儿

**一个 job 一个文件夹**，同名的话就在 `out/` 里：

```
out/
└── <job 的 name>/
    ├── gallery.html        # 静态模板总览（六个模板一页）
    ├── videogallery.html   # 视频模板总览（六个模板同时播放）
    ├── stills/             # 六张静态图 + 成品图
    │   ├── editorial.png
    │   ├── ...
    │   └── <job-name>.png
    └── videos/             # 六段模板视频 + 成品视频
        ├── editorial.mp4
        ├── ...
        └── <job-name>--3x4.mp4
```

`out/` 整个被 gitignore —— 产物是产物，不进仓库。

---

## 主题（配色层）

主题是"接进来"的一层：换品牌只改 theme 文件，模板和流程一个字都不用动。

仓库里只带一份 **`neutral`**（中性占位，深底 + 一个强调色，谁 clone 下来都能直接用）。
接自己的品牌：**复制一份改 token 就行**，详见 [themes/README.md](themes/README.md)。

```json
"tokens": { "accent": "#XXXXXX", "bg": "#XXXXXX" }
```

| token | 作用 |
|---|---|
| `bg` / `bg2` | 底色 / 次级底色 |
| `ink` / `inkSoft` | 正文色 / 弱化文字色 |
| `accent` / `accent2` | 强调色 / 次强调色（高亮、下划线、进度条） |
| `rule` | 分隔线 |
| `plate` / `platePad` / `plateRadius` | 引文所在的那块"面板"：底色、内边距、圆角。`transparent` = 引文直接落在页面底色上 |
| `onPlate` / `onPlateSoft` | 压在面板上的字色（引文 / 已念过的暗色句） |
| `onField` | 直接落在页面底色上的字色（署名、标题、标签） |
| `onAccent2` | 压在 accent2 色块上的字色（marker 的荧光笔） |
| `mesh1` / `mesh2` | gradient 模板两块柔光的颜色 |
| `quoteStroke` / `quoteStrokeWidth` | 引文字形外面的一圈描边。用八向零模糊 shadow 拼的，不是 `-webkit-text-stroke` —— 后者会啃掉字形填充，粗体明显变细 |
| `quoteShadow` | 引文下面的柔光投影。跟描边二选一 |
| `bgGrad` | 整幅背景渐变，替代 bg/bg2 |
| `vignette` | gradient 模板的网格遮罩。**浅底主题必须改成提亮**，否则深色字会落在被压暗的色块上 |
| `pad` | 页边距（1:1 会自动 ×0.86，方卡竖向空间少 25%） |
| `paneQuote` | `split` 模板上半块主色占整帧的比例，默认 `"80%"`。**引文区必须写死高度** —— 跟着内容长高的话，`fit()` 的字号自适应永远判定"没溢出"，文字会冲出画面 |
| `lang` | `en` / `zh-CN`，切换中西文排版规则 |
| `quoteSize` / `quoteMinSize` | 字号基准与下限（超长会自动缩到下限） |
| `qmarkSize` / `qmarkOpacity` | 右上角大引号的字号和不透明度，默认 `150` / `0.13`。字号是像素值，跟着帧走，不随主题缩放 |
| `qmarkInset` / `qmarkColor` / `qmarkFont` | 引号离角的距离（默认 `70`）、颜色（默认 `var(--on-plate)`）、字体（默认 Georgia 衬线） |
| `logoWidth` / `logoHeight` | 左上角 logo 的盒子，默认 `240` / `84` 像素。宽度是主导 —— 横版字标按宽度走，高度只是不让它占掉整个角 |
| `logoScale` | 把整个盒子再乘一个数，默认 `1`。**只改宽度不改这个的话，高度上限会把 logo 卡住，等于什么都没发生** |

渲染时会自动做对比度检查，正文／强调色压在底色上低于阈值会打印警告。
带描边或投影时，引文那条会降级成 `note:` 而不是 `!` —— 字是描边在撑，不是颜色。

### 浅底为什么默认不用白字

"主色满版做底"这个要求照做，但**白字压主色常常只有 1.4:1 左右的对比度**，字是糊的。
所以浅底版的默认是**深色字压主色**（约 8:1，任何长度的句子都读得清）。

想用白字也行，得让它浮起来：

| 方向 | 结果 |
|---|---|
| **深色字压主色** | 对比度最高，长句短句都稳。**默认** |
| **白字 + 柔光投影** | 白字靠投影从主色里浮出来。字少时好看，长句还是前者稳 |
| 白字 + 描边 | 描边版好看但"扣" |
| 深色面板垫在白字下面 | 面板像贴上去的补丁 |

> **注意**：白字 + 投影是把字"浮"起来，不是变清楚了。短句（一两行）用白字版，
> 长句用深色字版。渲染时的对比度警告按实际数字说话，别靠眼睛判断。

### 每个模板单独调

同一套配色落到不同模板上，画的面不一样，所以主题文件里可以给每个模板写覆盖：

```json
"overrides": {
  "boldblock": { "accent": "#XXXXXX" },
  "split":     { "bg2": "#XXXXXX" },
  "photoframe": { "onPlate": "#FFFFFF", "photoGround": true }
}
```

合并顺序：`DEFAULTS` < 主题 < 主题的 `overrides[模板]` < job 的 `tokens`。
job 里的 token 优先级最高，改单个模板不用重开一份主题。

### 右上角那个大引号

六个模板的右上角默认是空的。想让它说"这是一句引用"，job 里开 `showQuoteMark`：

```json
"showQuoteMark": true
```

一个 150px 的衬线 `“`，压在引文**底下**（z-index 2，字抬到 3），13% 不透明度。
引文可以盖着它走 —— 13% 是纹理，不是要躲的东西。

三个约定：

- **默认不开**。房规是引文上方那条短横杠（`#mark`），大引号是更外放的选择，
  所以要显式开。
- **跟右上角序号互斥**。"01" 也在那个角上，同开就叠着。开引号时序号自动让位。
- **六个模板都有**。层级写在 `base.css` 里，模板不用管。

大小、颜色、位置都能用 token 改：`qmarkSize` / `qmarkOpacity` / `qmarkInset` /
`qmarkColor` / `qmarkFont`。

---

## 左上角的 logo

logo 占的是**原来 kicker 那个位置**（左上角）。job 里给一个文件路径：

```json
"logo": "../assets/my-logo-dark.png"
```

**logo 会把 kicker 顶掉** —— 一个角上放两套身份会打架，logo 是必须在那儿的那套。
（logo 加载失败时 kicker 会自动顶上，因为它只是被 CSS 藏起来。）

### 浅底用深色 logo，深底用浅色 logo

logo 的颜色写在**图片的像素里**，theme 不知道它长什么样，所以这一条只能靠约定 + 检查：

| 地面 | 用哪版 |
|---|---|
| 浅色主色、浅底 | **黑色 / 深色** logo |
| 深底、夜景、深色主色 | **白色 / 浅色** logo |
| 照片（photoframe） | 照片多半偏深，用**白色 / 浅色** |

一份 job 可以带**两版**，工具按这张卡实际的地面自动挑：

```json
"logo":       "../assets/my-logo-dark.png",    // 浅底用
"logoOnDark": "../assets/my-logo-white.png"    // 深底用
```

**地面是怎么定的**：模板压着照片（`photoframe`）就是深底，跟 theme 无关；
其他模板看 theme 的地面色 —— 深色 theme 要浅色 logo，浅色 theme 要深色 logo。
判断的不是"亮不亮"，是**哪个颜色在这个底上更跳**：
一块亮橙（#FF4D2E）看着亮，配深色 logo 才看得清。

`check` 会读 logo 的像素，算出它有多亮，再跟底色比，**该换 logo 就直接说**：

```
  logo: 浅底用 ../assets/my-logo-dark.png   颜色对得上底色
         另一版（深底用）：../assets/my-logo-white.png
```

底色和 logo 都太亮（或者都太暗）时会警告：`浅底配浅色 logo —— 换成黑色或深色 logo`。

---

## 字体

**用自己的字体不用改 theme，也不用改模板**：把字体文件丢进 [fonts/](fonts/) 就会自动生效。

```
fonts/YourFont-Regular.woff2
fonts/YourFont-Bold.woff2
```

支持 `.woff2` / `.woff` / `.ttf` / `.otf`，文件名里的家族名直接成为 CSS font-family。
渲染前会等 `document.fonts.ready`，不会出现"第一次渲染悄悄用了回退字体"。

theme 里的 `quoteFont` 写的是字体栈，栈里第一个是想要的，后面是回退：

```json
"quoteFont": "Your Font, Century Gothic, Arial, sans-serif"
```

> `fonts/` 空的时候，栈里的第一个其实没生效，会直接用第二个。

---

## 中英文排版

`lang` 决定用哪套规则，这两套是**相反**的：

- `zh-CN`：CLREQ 的中文规范，字距 0（密排），行高松（1.3–1.5）
- `en`：拉丁大字需要**负字距**（-0.018em），否则大字显松散；行高收紧到 1.14

不用手动设 `lang` 也可以，但显式写上更保险 —— 字体回退、断词、标点宽度都会跟着变。

---

## 尺寸与字号

```json
"ratio": "3:4",          // 3:4(默认 1080×1440) / 1:1(1080×1080) / 9:16(1080×1920)
"tokens": { "quoteScale": 1.3 }   // 全局字号旋钮
```

`ratio` 也可以写成**数组**，一次出多尺寸：

```json
"ratio": ["1:1", "3:4"]
```

| 画幅 | 像素 | 什么时候用 |
|---|---|---|
| `3:4` | 1080×1440 | **竖版默认**。1080 宽，比 9:16 矮一截，正好放一句话 |
| `1:1` | 1080×1080 | 方卡，小红书图文首图 |
| `9:16` | 1080×1920 | 全屏竖屏。卡片只有一句话时上下都是空的，除非平台要求 |

多尺寸时文件名会自动带尺寸后缀（`<job>--1x1.png` / `<job>--3x4.png`），
单尺寸就是干净的文件名（`<job>.png`）。

命令行也能临时改，`--ratios` 优先级最高：

```bash
python build.py static jobs/example.json --ratios 1:1 3:4
python build.py video  jobs/example.json --ratios 3:4     # 只出竖版
```

`quoteScale` 是**乘在 theme 基准字号上的系数**，所有模板一起缩放：

| 值 | 效果 |
|---|---|
| `0.75` | 大字变小，行数变少，更适合短金句 |
| `1.0` | theme 里的基准字号 |
| `1.3` | 大字变大，更满、更抓眼 |

文案太长时字号会**自动缩小**，而且不报错 —— 想提前知道，跑 `python build.py check`。
视频用 `python build.py fit`（它量的是整支片子的最挤一屏，不是一张卡）。

视频画幅用 `video.ratios`（跟静态图同样的写法）单独设，不跟静态图的 `ratio` 联动。
`video.width` / `video.height` 也还在，但优先级最低。

---

## 六个模板

| 模板 | 长相 | 适合 |
|---|---|---|
| `editorial` | 杂志排版，细线、小标签、破折号署名 | 权威、沉淀、发布会金句 |
| `boldblock` | 整块主色，引文反白出来 | 短句、锐评、态度强的观点 |
| `split` | 上色块引文 / 下素底署名 | 长引文，色块保证对比度 |
| `marker` | 关键词马克笔高亮 + 手写下划线，右对齐 | 最像"截图会想存"的社交卡 |
| `gradient` | 柔和网格渐变，实色字 | 想要"现代感"但不浮夸 |
| `photoframe` | 上传自己的图 + 三段遮罩压字 | 人物照、发布会现场图 |

### 荧光笔：关键词由你指定

`marker` 模板的荧光笔是**运行时**贴上去的，关键词写在 job 的 `highlight` 里：

```json
"highlight": ["never the interesting ones", "all these models"]
```

- 关键词必须**和文案里的一段文字完全一致**（含空格、大小写）。
- 静态图在 `quote` 里找，视频在**每一条字幕**里找 —— 视频的词要出现在念出来的话里。
- `check` 会告诉你命中了几个、哪几个没命中：

```
  荧光笔  命中 2/3：never the interesting ones · all these models
          没命中（荧光笔不会出现在卡上）：single point
```

没命中不报错，但那一处**就是不会有荧光** —— 这是最容易被当成"工具坏了"的地方，
所以单独拎出来报。

### photoframe 一定有照片

`photoframe` 模板天生就是"放你自己的图"。job 不给图的时候，它会退到工具自带的
一张默认照片（`assets/demo-photo.jpg`，一位演讲者的现场照），
所以**这个模板永远不会是空框**。

给自己的图：

```json
"tokens": { "bgImage": "../assets/my-photo.jpg" }
```

遮罩强度会跟着主题走，浅底上传照片会自动换成提亮遮罩。

### 六个模板就是六个视频模板

没有"静态模板"和"视频模板"两套东西。**模板只负责画**，动效全在 `runtime.js` 里，
静态和视频共用同一份标记、同一套 token。视频是同六个模板的**一种播放模式**：

| | 静态 | 视频 |
|---|---|---|
| 文字从哪来 | job 的 `quote` | 音频转出来的 `cues` |
| 多了什么 | — | 逐句上屏、当前句高亮、已念的变暗、进度条 |
| 模板 | 六个 | **还是那六个** |

想一次看完六个模板动起来的样子：

```bash
python build.py videogallery jobs/example.json --clip 12
```

---

## job 文件

```jsonc
{
  "name": "example-quote",       // 输出文件夹名，也是文件名
  "template": "editorial",       // 上表任选其一
  "theme": "neutral",
  "ratio": ["1:1", "3:4"],       // 可以是数组，一次出多尺寸
  "scale": 2,                    // 超采样倍数，中文小字更干净

  "quote": "原句",
  "speaker": "Alex Doe, Platform Engineer",
  "title": "Engineering All-Hands 2026",
  "kicker": "KEYNOTE",           // 左上角小标签；给了 logo 就会被顶掉
  "logo": "../assets/demo/logo-white.png",        // 左上角 logo（顶掉 kicker）
  "logoOnDark": null,            // 深底用的那一版（photoframe 这类深地面）
  "showIndex": false,            // 右上角序号（"01"），默认显示
  "showQuoteMark": true,         // 右上角的大引号，默认不开
  "highlight": ["never the interesting ones"],  // 荧光笔关键词；写这里，不用改 HTML

  "audio": "../assets/speech.m4a",
  "cues":  "../assets/cues.json",
  "music": null,                 // 可选：铺一层背景乐，自动压到 musicGain
  "outDir": "../out",

  "tokens": { "quoteScale": 1.0, "bgImage": null },   // 任意 token 就地覆盖

  "video": {
    "fps": 30,
    "ratios": ["1:1", "3:4"],    // 视频画幅，可以跟静态图不一样
    "start": 4.6,                // 从音频第几秒开始
    "end": 13.0,                 // 到第几秒结束（不写就到底）
    "popMs": 300,                // 每句弹出的动画时长
    "lead": 0.05,                // 提前多久亮起
    "accumulate": true,          // 已念的句子留在上面（暗色）；false = 一次只显示当前句
    "keepLines": 4,              // 累加模式下同时留在屏上的句数（0 = 全部）
    "density": "compact",        // 行距更紧，视频里句子多时用
    "crf": 20
  }
}
```

---

## 加一个新模板

复制 `templates/editorial.html`，只写视觉，所有动效逻辑都在 `runtime.js` 里。

必须有的 id（`base.css` 已经给了默认样式）：

```
#stage #bg #bgImg #scrim #body #quote #mark #speaker #title #kicker #bar
```

可选的 `#logo`（左上角 logo）—— 放进去，job 里给了 `logo` 就会自动用上。

模板里放三个占位符：

- `<!--QC_BASE-->` — 共享基础样式（放在自己的 `<style>` 外面）
- `<!--QC_CONFIG-->` — 配置注入
- `<!--QC_RUNTIME-->` — 运行时（放最后）

字号用 `calc(var(--size-quote) * 1.2)` 这种相对写法，theme 的基准字号变了会自动跟着变。
`build.py` 每次会检查模板里引用的 CSS 变量是否都有定义，对不上会直接警告
（自定义属性没定义不会报错，只会让用到它的那条声明被静默丢掉）。

---

## 视频为什么这么渲染

逐帧截图 → ffmpeg 合成，而不是录屏，也不是烧 ASS 字幕：

- **不会漂**。每帧都是 `renderAt(t)` 的纯函数结果，`t` 直接来自音频时间轴，
  所以字幕和语音天然对齐，不需要任何补偿。
- **一套设计**。静态图和视频用的是同一个模板、同一份 token，配色改一次两边同时变。
- **成本为零**。ffmpeg 本来就要用来合音频，Playwright 本来就要用来出静态图。

速度参考：1080×1440 / 30fps，约 **110ms 一帧**（CPU）。
30 秒的片子 ≈ 100 秒渲染 + 几秒编码。换 `frameFormat: "png"` 会慢一些但无损。

字幕样式目前是「卡拉OK式」：整句留在屏幕上，当前句高亮、已念的句转暗。
这是中文短视频里做金句最稳的一种。要逐字扫光（ASS 的 `\kf`）得换实现，现有管线里没有。

### 屏上留几句？

`accumulate: true` 时已念的句子留在屏上变暗，但**不是全部都留** ——
`keepLines` 决定同时留在屏上的句数（当前句 + 前面几句）：

- 不写 `keepLines` = 0 → 整段话都往一屏塞，字号被压到看不清
- `keepLines: 1` → 只留当前句，等于 `accumulate: false` 的画面
- `keepLines: 4` → 当前句 + 前三句，前面的滚出画面（默认推荐值）

窗口开多大合适，看引文区装不装得下：`keepLines` 每加一句，字号就小一点。
拿不准就先量一下 —— `python build.py fit` 会告诉你字号定在哪、画面填不填得满。

### 字号整支视频只算一次

视频里字号**不随句子进出跳动**。启动时把每一种窗口组合都量一遍，
取装得下最挤那次的那档字号，整支片子都用它。

所以要改字号，改 `tokens.quoteScale`（整体缩放）就行 ——
不要指望某一屏能自动变大，位置留给引文区最挤的那一屏。

---

## 转写

`--model small` 是默认。中文 30 秒音频大约 10–15 秒转完（CPU，无 GPU）。

中文：`initial_prompt` 已内置简体中文偏置 —— 不加的话会输出繁体
（們/聰/定義 而不是 们/聪/定义）。英文加 `--language en`。

断句规则：句号叹号必断 → 停顿超过 `--max-gap` 必断 → 接近 `--max-chars`
时遇到逗号断。词不会被拦腰截断。转写难免有错字，选金句以 `cues.json` 为准，
手改就行。

---

## 仓库里有什么、没有什么

这套东西是**给别人用**的，所以仓库里不装任何人的品牌：

| 目录 | 里面是什么 |
|---|---|
| `themes/` | 只带一份 `neutral` 中性主题。自己的品牌主题放 `themes/_brand/`（已 gitignore） |
| `assets/demo/` | 假数据：合成的人声、一段编出来的字幕、一个自己画的字标 |
| `assets/demo-photo.jpg` | `photoframe` 的默认照片（一位演讲者的现场照），job 不给图时兜底 |
| `assets/_brand/` | 自己的 logo、音频、照片（已 gitignore） |
| `jobs/example.json` | 唯一会进仓库的 job，speaker 是占位名 `Alex Doe` |

`jobs/` 下的其他 job、`out/` 全部、`assets/_brand/`、`themes/_brand/` 都被 gitignore 挡掉。
**发到 GitHub 之前不用手动清理**，`git status` 里看不到它们。

> 音频和 logo 建议做成**白底 + 黑字**的 PNG/JPG，透明背景最省事。

---

## 文件

```
build.py          命令行入口
runtime.js        所有动效/自适应逻辑，模板不用碰
base.css          共享骨架 + 中英文排版规则
tokens.py         配色合并 + 对比度检查
templates/*.html  六个模板，纯视觉
themes/           配色层：neutral（通用）+ _brand/（你自己的，已 gitignore）
fonts/            丢字体文件进来就自动生效
jobs/             一条金句一个文件（只有 example.json 会进仓库）
assets/           图片和音频（demo/ 是假数据，_brand/ 是你自己的）
SKILL.md          当作 skill 用时的入口说明
README.md         这个文件
LICENSE           MIT
requirements.txt  Python 依赖（ffmpeg 不在里面，是系统程序）
docs/WORKFLOW.md  完整制作流程
docs/flow.png     流程图
docs/flow.html    流程图源码（浏览器直接能开）
docs/flow.mmd     流程图的 mermaid 版
diagram.py        把流程图渲染成 PNG（HTML 或 mermaid 都收）
.cache/           mermaid.js 的本地缓存（第一次跑 diagram.py 时自动下载，之后离线可用）
```
