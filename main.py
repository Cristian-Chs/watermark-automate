import io
import logging
import os
from PIL import Image, ImageDraw
from dotenv import load_dotenv

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# Cargar variables de entorno desde el archivo .env
load_dotenv()

# --- CONFIGURACIÓN (Vía Variables de Entorno) ---
TOKEN = os.getenv("BOT_TOKEN")
LOGO_PATH = os.getenv("LOGO_PATH", "logo.png")
WATERMARK_RATIO = float(os.getenv("WATERMARK_RATIO", 0.15))
MARGIN = int(os.getenv("MARGIN", 20))
LOGO_OPACITY = float(os.getenv("LOGO_OPACITY", 0.25))

# Configuración de despliegue
PORT = int(os.environ.get("PORT", 8443))
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")

# Configuración del sistema de logs
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

def process_logo(logo_path, opacity=0.5):
    """
    Carga el logo, elimina el fondo blanco circular y ajusta la opacidad.
    """
    if not os.path.exists(logo_path):
        raise FileNotFoundError(f"No se encontró el archivo '{logo_path}'.")

    logo = Image.open(logo_path).convert("RGBA")
    width, height = logo.size
    
    # --- Transparencia Inteligente: Máscara Circular ---
    mask = Image.new('L', (width, height), 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((0, 0, width, height), fill=255)
    logo.putalpha(mask)
    
    # --- Refinado: Eliminar fondo blanco interno ---
    data = logo.getdata()
    new_data = []
    for item in data:
        if item[0] > 245 and item[1] > 245 and item[2] > 245:
            new_data.append((255, 255, 255, 0))
        else:
            new_data.append(item)
    logo.putdata(new_data)

    # --- Ajuste de Opacidad ---
    if opacity < 1.0:
        alpha = logo.getchannel('A')
        alpha = alpha.point(lambda p: int(p * opacity))
        logo.putalpha(alpha)

    return logo

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja el comando /start"""
    await update.message.reply_text(
        "👋 ¡Bienvenido al Bot de Marcas de Agua!\n\n"
        "Envíame cualquier foto y te la devolveré con el sello del "
        "Kinder Store aplicado automáticamente."
    )

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja la recepción de fotos y aplica la marca de agua"""
    await update.message.reply_chat_action("upload_photo")
    
    try:
        # 1. Obtener la foto
        photo_file = await update.message.photo[-1].get_file()
        
        # 2. Descargar a memoria
        photo_bytes = await photo_file.download_as_bytearray()
        user_img = Image.open(io.BytesIO(photo_bytes)).convert("RGB")
        user_w, user_h = user_img.size
        
        # 3. Procesar logo
        logo = process_logo(LOGO_PATH, opacity=LOGO_OPACITY)
        
        # 4. Escalar
        new_logo_w = int(user_w * WATERMARK_RATIO)
        aspect_ratio = logo.size[1] / logo.size[0]
        new_logo_h = int(new_logo_w * aspect_ratio)
        logo_resized = logo.resize((new_logo_w, new_logo_h), Image.Resampling.LANCZOS)
        
        # 5. Estampar en cuadrícula 4x4
        for row in range(4):
            for col in range(4):
                cell_center_x = (user_w // 4) * col + (user_w // 8)
                cell_center_y = (user_h // 4) * row + (user_h // 8)
                pos_x = cell_center_x - (new_logo_w // 2)
                pos_y = cell_center_y - (new_logo_h // 2)
                user_img.paste(logo_resized, (pos_x, pos_y), logo_resized)
        
        # 6. Preparar envío
        output = io.BytesIO()
        user_img.save(output, format="JPEG", quality=90)
        output.seek(0)
        
        await update.message.reply_photo(photo=output, caption="✅ Imagen procesada con éxito.")
        
    except Exception as e:
        logging.error(f"Error en el procesamiento: {e}")
        await update.message.reply_text("❌ Ocurrió un error al procesar tu imagen.")

if __name__ == '__main__':
    if not TOKEN:
        print("ERROR: No se encontró BOT_TOKEN en el archivo .env o variables de entorno.")
        exit(1)

    application = ApplicationBuilder().token(TOKEN).build()
    
    application.add_handler(CommandHandler('start', start))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    
    if WEBHOOK_URL:
        # MODO PRODUCCIÓN (WEBHOOKS)
        print(f"--- Iniciando en modo WEBHOOK (Puerto {PORT}) ---")
        application.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path=TOKEN,
            webhook_url=f"{WEBHOOK_URL}/{TOKEN}"
        )
    else:
        # MODO DESARROLLO (POLLING)
        print("--- Iniciando en modo POLLING (Local) ---")
        application.run_polling()
