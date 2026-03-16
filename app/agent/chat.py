"""
chat.py
───────
LexiGraph Legal Assistant — Interactive Terminal Chat Application.

Kullanıcıya interaktif bir terminal arayüzü sunar.
MCP sunucuları üzerinden Neo4j ve Qdrant veritabanlarına bağlanarak
sözleşme analizi yapan bir AI asistanla sohbet edilmesini sağlar.

Kullanım:
    python -m app.agent.chat
    python -m app.agent.chat --user emrullah --session my-session
"""

import argparse
import asyncio
import sys
import uuid
from datetime import datetime

from app.agent.agno_agent import create_agent


# ─── ANSI Renk Kodları ────────────────────────────────────────────────────────

class Colors:
    RESET    = "\033[0m"
    BOLD     = "\033[1m"
    DIM      = "\033[2m"
    CYAN     = "\033[36m"
    GREEN    = "\033[32m"
    YELLOW   = "\033[33m"
    RED      = "\033[31m"
    MAGENTA  = "\033[35m"
    BLUE     = "\033[34m"
    BG_DARK  = "\033[48;5;234m"


# ─── Yardımcı Fonksiyonlar ────────────────────────────────────────────────────

def print_banner() -> None:
    """Uygulama başlık banner'ını yazdırır."""
    banner = f"""
{Colors.CYAN}{Colors.BOLD}
╔══════════════════════════════════════════════════════════════════╗
║                                                                  ║
║     ██╗     ███████╗██╗  ██╗██╗ ██████╗ ██████╗  █████╗ ██████╗ ║
║     ██║     ██╔════╝╚██╗██╔╝██║██╔════╝ ██╔══██╗██╔══██╗██╔══██╗║
║     ██║     █████╗   ╚███╔╝ ██║██║  ███╗██████╔╝███████║██████╔╝║
║     ██║     ██╔══╝   ██╔██╗ ██║██║   ██║██╔══██╗██╔══██║██╔═══╝ ║
║     ███████╗███████╗██╔╝ ██╗██║╚██████╔╝██║  ██║██║  ██║██║     ║
║     ╚══════╝╚══════╝╚═╝  ╚═╝╚═╝ ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝ ║
║                                                                  ║
║          {Colors.YELLOW}⚖️  Legal Contract Analysis Assistant  ⚖️{Colors.CYAN}            ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝
{Colors.RESET}"""
    print(banner)


def print_info(user_id: str, session_id: str) -> None:
    """Oturum bilgilerini yazdırır."""
    print(f"{Colors.DIM}{'─' * 66}{Colors.RESET}")
    print(f"  {Colors.GREEN}▸ User    :{Colors.RESET} {user_id}")
    print(f"  {Colors.GREEN}▸ Session :{Colors.RESET} {session_id}")
    print(f"  {Colors.GREEN}▸ Time    :{Colors.RESET} {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{Colors.DIM}{'─' * 66}{Colors.RESET}")
    print()
    print(f"  {Colors.YELLOW}📖 Komutlar:{Colors.RESET}")
    print(f"     {Colors.CYAN}/help{Colors.RESET}    — Bu yardım menüsünü göster")
    print(f"     {Colors.CYAN}/clear{Colors.RESET}   — Ekranı temizle")
    print(f"     {Colors.CYAN}/new{Colors.RESET}     — Yeni oturum başlat")
    print(f"     {Colors.CYAN}/quit{Colors.RESET}    — Çıkış yap  (veya Ctrl+C)")
    print()
    print(f"  {Colors.DIM}MCP Sunucuları: Neo4j (Graph DB) + Qdrant (Vector DB){Colors.RESET}")
    print(f"  {Colors.DIM}Sözleşmeleri analiz etmek için sorularınızı yazın.{Colors.RESET}")
    print()


def print_help() -> None:
    """Yardım menüsünü gösterir."""
    print(f"""
{Colors.YELLOW}{'═' * 50}
  LexiGraph — Yardım Menüsü
{'═' * 50}{Colors.RESET}

  {Colors.CYAN}Komutlar:{Colors.RESET}
    /help        Bu menüyü göster
    /clear       Ekranı temizle
    /new         Yeni oturum başlat (geçmiş sıfırlanır)
    /quit        Programdan çık

  {Colors.CYAN}Örnek Sorular:{Colors.RESET}
    • Veritabanında kaç sözleşme var?
    • Non-compete clause içeren sözleşmeleri listele.
    • "MARKETING AFFILIATE AGREEMENT" sözleşmesinin tarafları kimler?
    • License Agreement türündeki sözleşmeleri göster.
    • California hukukuna tabi sözleşmeleri bul.
    • Indemnification hakkında hangi sözleşmelerde bilgi var?
    • Exclusivity clause olan sözleşmeleri Cypher sorgusu ile bul.

  {Colors.CYAN}İpuçları:{Colors.RESET}
    • Yapısal sorular (taraf, tür, tarih) → Neo4j kullanılır
    • İçerik aramaları (madde, kloz metni) → Qdrant kullanılır
    • Agent her iki veritabanını da otomatik seçer
""")


# ─── Ana Chat Döngüsü ─────────────────────────────────────────────────────────

async def chat_loop(user_id: str, session_id: str) -> None:
    """Ana interaktif sohbet döngüsü."""

    agent = create_agent(user_id=user_id, session_id=session_id)

    while True:
        try:
            # Kullanıcı girdisi
            print(f"{Colors.GREEN}{Colors.BOLD}  You ▸{Colors.RESET} ", end="")
            user_input = input().strip()

            # Boş girdi
            if not user_input:
                continue

            # ── Komutlar ──────────────────────────────────────────────────
            cmd = user_input.lower()

            if cmd in ("/quit", "/exit", "/q"):
                print(f"\n  {Colors.MAGENTA}👋 Görüşmek üzere!{Colors.RESET}\n")
                break

            if cmd == "/help":
                print_help()
                continue

            if cmd == "/clear":
                print("\033[2J\033[H", end="")  # ANSI clear screen
                print_banner()
                print_info(user_id, session_id)
                continue

            if cmd == "/new":
                session_id = str(uuid.uuid4())[:8]
                agent = create_agent(user_id=user_id, session_id=session_id)
                print(f"\n  {Colors.YELLOW}🔄 Yeni oturum başlatıldı: {session_id}{Colors.RESET}\n")
                continue

            # ── Agent'a sor ───────────────────────────────────────────────
            print()
            print(f"  {Colors.CYAN}{Colors.BOLD}  LexiGraph ▸{Colors.RESET} ", end="")
            print()  # Yanıt için yeni satır

            await agent.aprint_response(
                user_input,
                stream=True,
                markdown=True,
                show_full_reasoning=True,
            )

            print()  # Yanıt sonrası boşluk

        except KeyboardInterrupt:
            print(f"\n\n  {Colors.MAGENTA}👋 Görüşmek üzere!{Colors.RESET}\n")
            break
        except EOFError:
            print(f"\n\n  {Colors.MAGENTA}👋 Görüşmek üzere!{Colors.RESET}\n")
            break
        except Exception as e:
            print(f"\n  {Colors.RED}❌ Hata: {e}{Colors.RESET}\n")


# ─── Entry Point ──────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="LexiGraph Legal Assistant — Terminal Chat",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Örnekler:
  python -m app.agent.chat
  python -m app.agent.chat --user emrullah
  python -m app.agent.chat --user emrullah --session my-session
        """,
    )
    parser.add_argument(
        "--user", "-u",
        default="default",
        help="Kullanıcı kimliği (varsayılan: default)",
    )
    parser.add_argument(
        "--session", "-s",
        default=None,
        help="Oturum kimliği (varsayılan: yeni UUID)",
    )

    args = parser.parse_args()

    user_id = args.user
    session_id = args.session or str(uuid.uuid4())[:8]

    # Banner ve bilgi
    print_banner()
    print_info(user_id, session_id)

    # Chat döngüsünü başlat
    try:
        asyncio.run(chat_loop(user_id, session_id))
    except KeyboardInterrupt:
        print(f"\n\n  {Colors.MAGENTA}👋 Görüşmek üzere!{Colors.RESET}\n")
        sys.exit(0)


if __name__ == "__main__":
    main()
