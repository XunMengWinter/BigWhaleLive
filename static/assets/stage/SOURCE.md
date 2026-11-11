# 海底打工舞台背景

## 当前 v2（2026-11-09）

- 文件：`ocean-office-v2.jpg`；1080×1920，217054 字节，JPG。
- SHA-256：`379aaf1a96208c533138d104502e59be00ca995678919dc20ddb613967d61517`。
- 内置 Image Gen 基于 v1 编辑生成，新增黄铜舷窗、海底光束、墙面灯饰、绿植与笔记本；无角色和可读文字。原始941×1672，ffmpeg等比放大与极小居中裁切后导出JPG。
- 桌沿仍在83%附近；电脑和墙钟为独立HTML实时元素，不在底图内烘焙。角色素材、声线与各自授权不变。v1保留用于历史追溯。

最终提示：

```text
Use case: illustration-story. Edit target: existing ocean-office-v1 background. Create a much more beautiful polished 2D anime underwater office background for a portrait 9:16 livestream, 1080x1920 composition. Preserve warm honey wood desk spanning full width with horizontal back edge at exactly 83% image height and teal/sea-blue atmosphere. No characters, fish characters, people or silhouettes. Replace the plain background with a cozy undersea research office: elegant large round submarine porthole centered at x50%, y49%, diameter 70% image width, sea-blue water with soft sunbeams and distant coral visible through glass, warm brass rim; subtle painted teal wall panels, little warm lights, tasteful cel shaded texture. Top 34% stays quiet dark teal negative space for existing large text overlays. Center from y45 to y77% stays very uncluttered for a large whale character layered afterward. Remove the existing computer at left completely; leave desktop clear: an editable real-time HTML monitor will be overlaid in foreground at x14-52%, y72-87%. Do NOT draw a computer, keyboard or clock. Reserve quiet bare wall at x72%, y40% for a small wall clock overlaid separately. Small charming potted seaweed on far left near desk, cream whale motif mug at lower right on desk, a small closed notebook on right lower desktop. Keep props understated. Fine dark-blue linework, gentle golden lighting and turquoise caustics, richly designed but restful. Not photorealistic or 3D. No text, letters, numbers, logos, panels, UI, watermarks. Full bleed 9:16 portrait.
```

## 历史 v1

- 文件：`ocean-office-v1.jpg`
- 规格：1080 × 1920，9:16，JPG，114370 字节。
- SHA-256：`df3d6ec708533535cdff1b9952abd660509191b9c0ebfc2aa01a2b3b5833d09d`
- 生成日期：2026-11-08。
- 生成方式：内置 Image Gen，用户附件仅作为色彩、画风及桌面构图参考。
- 原始生成尺寸：941 × 1672；使用 ffmpeg 等比放大与极小居中裁切为 1080 × 1920，再导出高质量 JPG。未用代码绘制场景。
- 画面：海蓝与青绿的动漫海底办公室、气泡、左侧显示器、温暖木桌与右侧杯子。没有角色、平台界面、可读文字、数据或商标。
- 定位：桌面后沿约在画面高度的 83%；角色可叠加在中下方空白处，UI 使用独立可编辑层。
- 该图是正式舞台运行素材；原始生成缓存和过程截图不加入 Git。用户提供的参考截图不作为本站背景直接分发。
- dsh-pet 角色素材仍遵循其独立来源与授权，不由此背景说明替代。

## 最终生成提示

```text
Use case: illustration-story.
Asset type: production background image for a portrait 9:16 animated livestream stage, 1080 x 1920 composition.
Input image 1 is a STYLE AND COMPOSITION REFERENCE ONLY: use its flat anime underwater-office atmosphere, teal and sea-blue palette, and a wooden desk near the bottom. Do not reproduce the app UI, text, character, badges, mobile navigation, logos or gifts.
Create one clean original 2D anime/cel-shaded underwater programmer office backdrop. No characters, no people, no silhouettes.
Composition: the top 55% of the image is generous uncluttered deep teal-blue negative space, with subtle underwater light and a few soft small translucent bubbles. The wood desk spans the entire width; its back edge is a straight horizontal line at exactly about 80% of the image height. The visible warm wood tabletop fills the remaining bottom 20%, with refined horizontal wood grain.
A modest dark computer monitor occupies only the lower-left area between 65% and 80% image height, with its stand ending at the desk back edge. On its screen are tiny multicolored abstract code strokes, absolutely no legible text. At the far lower-right is one small cream ceramic mug with an understated ocean motif, resting naturally on the tabletop. Keep the center and center-right area from 45% to 80% completely clean for an existing animated chibi character to be composited later. No keyboard.
Style: polished clean hand-drawn flat anime background, soft cel shading, dark blue thin outlines, comfortable quiet working mood, restrained texture, predominantly muted #19576d / #216d7e / #2d8090 blues with warm honey brown desk. Avoid photorealism, 3D rendering, elaborate room furniture, windows, large plants, any UI panels, borders, labels, numbers, readable text, logos and watermarks.
The asset itself must be portrait 9:16 with no margins or mockup framing.
```

