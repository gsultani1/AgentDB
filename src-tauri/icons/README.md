# Icons

Place application icons here before building:

- `32x32.png` — 32x32 pixels
- `128x128.png` — 128x128 pixels
- `128x128@2x.png` — 256x256 pixels (Retina)
- `icon.icns` — macOS icon bundle
- `icon.ico` — Windows icon
- `icon.png` — System tray icon (recommended 32x32 or 64x64)

Generate all sizes from a single source image using:

```bash
npx tauri icon /path/to/source-image.png
```

This requires a 1024x1024+ PNG as input.
