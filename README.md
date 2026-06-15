# Job Search Pipeline

Script para buscar ofertas en Adzuna y LinkedIn, filtrar por España remoto y Barcelona híbrido, y descartar roles en inglés, junior, técnico y devops.

## Uso

1. Crea un archivo `.env` en la raíz del proyecto con tus credenciales privadas:
   ```text
   APP_ID=tu_app_id
   APP_KEY=tu_app_key
   ```
2. Alternativamente, exporta las variables de entorno `APP_ID` y `APP_KEY`.
3. Ejecuta:
   ```bash
   python main.py
   ```

> El archivo `.env` no debe subirse al repositorio. Usa `.env.example` como plantilla para compartir la configuración sin credenciales.

## Excluir

- No se suben a GitHub archivos de logs ni CSV generados.
- No se suben entornos virtuales ni secretos.
