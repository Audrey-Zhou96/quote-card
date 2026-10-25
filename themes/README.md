# themes —— 配色层

一个 theme 文件就是一套配色。**换品牌只改这里，模板和流程一个字都不用动。**

## 这里面有什么

| 文件 | 角色 | 谁用 |
|---|---|---|
| `neutral.json` | 中性深底 + 一个强调色 | **通用**。谁 clone 下来都能直接跑，不需要改任何东西 |
| `_brand/pangea-bright.json` | 浅底版：主色满版做底，引文用深色压在上面 | 本仓库作者自己的品牌 |
| `_brand/pangea-bright-white.json` | 浅底版 · 白字 + 柔光投影 | 同上 |
| `_brand/pangea-dark.json` | 深底版：主色只做强调 | 同上 |

> `_brand/` 整个目录是 **gitignore 掉的**。
> 里面是作者本人的品牌色，跟工具本身没关系 —— 开源发布时它们压根不会被提交，
> 剩下的只有 `neutral.json`，六个模板照样跑得通。
>
> 要留一个当"浅底版长什么样"的例子也行，但得先把它从 `_brand/` 挪出来，
> **并且把里面的色值换成你自己的**。
>
> 品牌素材是成套的：`themes/_brand/` 走的是 `assets/_brand/`（logo、音频、演讲稿），
> 两边一起换。

## 接自己的品牌

**一、复制一份**

```bash
cp themes/neutral.json themes/my-brand.json
```

**二、改色值**（token 名的意思见 [docs/REFERENCE.md](../docs/REFERENCE.md#配色token)）

```json
{
  "bg": "#XXXXXX",        // 底色
  "bg2": "#XXXXXX",       // 次级底色
  "ink": "#XXXXXX",       // 正文色
  "inkSoft": "#XXXXXX",   // 弱化文字色
  "accent": "#XXXXXX",    // 强调色（高亮、下划线、进度条）
  "accent2": "#XXXXXX",   // 次强调色（荧光笔）
  "rule": "#XXXXXX",      // 分隔线
  "quoteFont": "Your Font, Arial, sans-serif",
  "metaFont":  "Your Font, Arial, sans-serif"
}
```

**三、字体丢进 `fonts/`** —— 文件名里的家族名直接成为 CSS font-family，
theme 里写 `"quoteFont": "Your Font, Arial, sans-serif"` 就能用上。
`fonts/` 空的时候栈里的第一个不生效，会直接掉到第二个。

**四、每个模板单独调**（可选）—— 同一套配色落到六个模板上，画的面不一样：

```json
"overrides": {
  "boldblock": { "accent": "#XXXXXX" },
  "split":     { "bg2": "#XXXXXX" },
  "photoframe": { "onPlate": "#FFFFFF", "photoGround": true }
}
```

**五、job 里点名**

```json
"theme": "my-brand"
```

## 浅底还是深底

| | 什么时候用 | 注意 |
|---|---|---|
| 浅底（主色满版） | 想要"品牌色铺满整张卡" | 白字压主色常常只有 1.4:1，对比度不够。默认用深色字压主色 |
| 深底（近黑 + 主色点缀） | 长句、夜景、想要克制 | 长句最稳，主色只做强调 |

渲染时会自动做对比度检查，低于阈值会打印警告 —— **按警告改，别靠眼睛判断**。

## 合并顺序

```
DEFAULTS（tokens.py） < 主题 < 主题的 overrides[模板] < job 的 tokens
```

job 里的 token 优先级最高，所以改单个模板的颜色不用新开一份主题。
