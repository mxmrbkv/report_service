import re
import os

with open('app/static/index.html', 'r', encoding='utf-8') as f:
    content = f.read()

style_match = re.search(r'<style>(.*?)</style>', content, re.DOTALL)
if style_match:
    with open('app/static/style.css', 'w', encoding='utf-8') as f:
        f.write(style_match.group(1).strip())

script_match = re.search(r'<script>(.*?)</script>', content, re.DOTALL)
if script_match:
    with open('app/static/app.js', 'w', encoding='utf-8') as f:
        f.write(script_match.group(1).strip())

new_html = re.sub(r'<style>.*?</style>', '<link rel=\"stylesheet\" href=\"/static/style.css\">', content, flags=re.DOTALL)
new_html = re.sub(r'<script>.*?</script>', '<script src=\"/static/app.js\"></script>', new_html, flags=re.DOTALL)

with open('app/static/index.html', 'w', encoding='utf-8') as f:
    f.write(new_html)
