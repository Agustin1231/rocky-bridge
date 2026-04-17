# Playwright en Mac Mini — Guía de instalación y uso

## ¿Qué es Playwright?

Playwright es una librería de automatización de navegadores (Chrome, Firefox, Safari). Permite hacer screenshots, grabar videos de páginas web, y automatizar interacciones — todo desde código Python o Node.js.

---

## Instalación en Mac Mini

### Requisitos previos

```bash
# Verificar Python (necesitas 3.8+)
python3 --version

# Verificar pip
pip3 --version
```

### 1. Instalar Playwright

```bash
pip3 install playwright
```

### 2. Instalar los navegadores

```bash
playwright install chromium
# O instalar todos:
playwright install
```

### 3. Verificar instalación

```bash
python3 -c "from playwright.sync_api import sync_playwright; print('OK')"
```

---

## Uso básico

### Screenshot de una página

```python
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    page.goto("https://bridge.agustinynatalia.site")
    page.screenshot(path="screenshot.png")
    browser.close()
    print("Screenshot guardado")
```

### Grabar video de una página

```python
import asyncio
from playwright.async_api import async_playwright

async def grabar():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            record_video_dir="./videos/",
            record_video_size={"width": 1280, "height": 800}
        )
        page = await context.new_page()
        await page.goto("https://bridge.agustinynatalia.site")
        await asyncio.sleep(2)

        # Scroll suave hacia abajo
        for y in range(0, 600, 40):
            await page.evaluate(f"window.scrollTo(0, {y})")
            await asyncio.sleep(0.08)

        await asyncio.sleep(1)
        await context.close()  # El video se guarda aquí
        await browser.close()
        print("Video guardado en ./videos/")

asyncio.run(grabar())
```

### Abrir página local (HTML file)

```python
page.goto("file:///ruta/completa/al/archivo.html")
```

---

## Ejecutar en modo headless (sin ventana)

Por defecto Playwright corre sin ventana (headless). Si necesitas ver el navegador:

```python
browser = p.chromium.launch(headless=False)
```

---

## Problemas comunes en Mac

### Error: "Executable doesn't exist"
```bash
playwright install chromium
```

### Error de permisos en macOS
```bash
# Dar permisos al binario de Chromium
xattr -d com.apple.quarantine $(python3 -c "import playwright; print(playwright.__file__.replace('__init__.py',''))")ms/chromium*/chrome-mac/Chromium.app/Contents/MacOS/Chromium 2>/dev/null || true
```

### Mac Apple Silicon (M1/M2/M3)
Playwright soporta Apple Silicon nativamente desde v1.18. Asegúrate de tener la versión más reciente:
```bash
pip3 install --upgrade playwright
playwright install chromium
```

---

## Formatos de video soportados

| Formato | Extensión | Compatibilidad |
|---------|-----------|---------------|
| WebM (default) | `.webm` | Chrome, Firefox, Edge |
| Para convertir a MP4 | usar ffmpeg | Universal |

### Convertir WebM a MP4 (opcional)
```bash
# Instalar ffmpeg
brew install ffmpeg

# Convertir
ffmpeg -i video.webm -c:v libx264 -c:a aac video.mp4
```

---

## Recursos

- Docs oficiales: https://playwright.dev/python/
- Versión actual: `playwright --version`
