# fonts/

把字体文件丢进这个目录就会自动生效，不需要改 theme 也不用改模板。

命名：`家族名-字重.扩展名`，例如

```
YourFont-Regular.woff2
YourFont-Medium.woff2
YourFont-Bold.woff2
YourFont-Black.woff2
```

支持 `.woff2` / `.woff` / `.ttf` / `.otf`。
识别的字重：Thin(100) / ExtraLight(200) / Light(300) / Regular(400) /
Medium(500) / SemiBold(600) / Bold(700) / ExtraBold(800) / Black(900)。
认不出来就当 Regular(400)。

文件名里的家族名会直接成为 CSS font-family，所以 `YourFont-Bold.woff2`
对应的 font-family 是 `YourFont`，正好和 theme 里的
`"quoteFont": "YourFont, Arial, sans-serif"` 对上。

**没放字体文件的时候，栈里的第一个其实不生效** —— 会直接掉到第二个。
所以 theme 里写字体栈的时候，第二个要挑一个本机一定有的回退。

渲染前会等 `document.fonts.ready`，所以不会出现"第一次渲染悄悄用了回退字体"。
