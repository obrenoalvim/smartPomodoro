"""Converte logo.png em pomodoro.ico para janela, exe e instalador."""
from PIL import Image

def main():
    src = Image.open("logo.png").convert("RGBA")
    sizes = [16, 32, 48, 64, 128, 256]
    frames = [src.resize((s, s), Image.LANCZOS) for s in sizes]
    frames[0].save("pomodoro.ico", format="ICO",
                   append_images=frames[1:],
                   sizes=[(s, s) for s in sizes])
    print("OK: pomodoro.ico gerado")

if __name__ == "__main__":
    main()
