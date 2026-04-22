---
name: Reglas de trabajo en mundotec-networking
description: Comportamientos requeridos y prohibidos al trabajar en este proyecto
type: feedback
---

# Reglas de trabajo

## LEER CONTEXTO PRIMERO
Antes de tocar cualquier archivo del proyecto, leer `/home/lroot/mundotec-networking/BITACORA.md` y la memoria `project_estado.md`. El proyecto tiene sprints acumulados — hacer cambios sin contexto borra trabajo avanzado.

**Why:** En múltiples sesiones se perdió contexto causando regresiones, re-trabajo y 2+ horas perdidas en una sola sesión (2026-04-22).
**How to apply:** Primera acción de cualquier sesión = leer BITACORA.md. No asumir que el código está "en blanco".

## NO SOBREESCRIBIR static/index.html COMPLETO
El HTML es un archivo de ~2500+ líneas con toda la SPA. Usar Edit para cambios puntuales, NUNCA Write para reescribir completo a menos que el usuario lo pida explícitamente.

**Why:** Reescribir el HTML borra secciones enteras ya implementadas (IPAM, fibra, credenciales, reportes, etc.).
**How to apply:** Siempre Edit con contexto suficiente para ser único. Verificar con grep que no hay duplicados después.

## VERIFICAR JS ANTES DE COMMITEAR
Después de cualquier cambio en index.html, verificar que no hay declaraciones `let`/`const` duplicadas en el bloque `<script>`. Un duplicado rompe TODA la página.

**Why:** Sprint 5 introdujo `let _impFile` duplicado → SyntaxError → login roto → 2h de debugging.
**How to apply:** `grep -n "^let \|^const " static/index.html | sort | uniq -d` antes de commit.

## PASSWORDS — NO ASUMIR
No asumir que la contraseña del admin es la del código (`Admin123!`). Verificar con `verify_pw` directamente.

**Why:** La BD puede tener un hash diferente al del código si el usuario la cambió o si un seed la pisó.
**How to apply:** Si hay problemas de login, siempre verificar el hash real antes de resetear.

## STATIC FILES NO NECESITAN RESTART
Los archivos en `static/` se sirven desde disco por FastAPI StaticFiles. Un cambio en `index.html` aplica inmediatamente sin reiniciar uvicorn.

**Why:** Se pierde tiempo innecesariamente reiniciando el servicio cuando no es necesario.
**How to apply:** Solo reiniciar cuando cambian archivos `.py` (routers, models, main.py, etc.).

## VERIFICAR JS DESPUÉS DE CADA CAMBIO EN index.html
Antes de commitear cualquier cambio en `static/index.html`, ejecutar:
```bash
python3 -c "
import re,subprocess
with open('static/index.html') as f: c=f.read()
s=re.findall(r'<script[^>]*>(.*?)</script>',c,re.DOTALL)
r=subprocess.run(['node','--input-type=module'],input=s[0],capture_output=True,text=True)
print('ERROR:'+r.stderr[:300] if r.returncode!=0 and 'localStorage' not in r.stderr else 'JS OK')
"
```

**Why:** Dos veces se rompió el login completo por errores JS (let duplicado, ternario incompleto). El error JS en el único `<script>` bloquea TODA la página.
**How to apply:** Obligatorio antes de cada `git commit` que toque `index.html`.
