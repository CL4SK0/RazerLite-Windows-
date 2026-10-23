"""RazerLite en ligne de commande. Sans argument, ouvre l'interface graphique."""

import argparse
import sys
import time
from pathlib import Path

from . import __version__, profiles
from .devices import RazerError, backend, enumerate_raw, find_devices

KINDS = {"souris": "mouse", "mouse": "mouse", "clavier": "keyboard", "keyboard": "keyboard",
         "casque": "headset", "headset": "headset"}


def pick(devices, name):
    kind = KINDS.get(name.lower())
    for d in devices:
        if d.kind == kind:
            return d
    raise RazerError(f"Aucun appareil « {name} » détecté (lance « razerlite list »).")


def cmd_list(args, devices):
    if not devices:
        print("Aucun périphérique Razer reconnu. Lance « razerlite diag » et envoie le fichier généré.")
    for d in devices:
        print(f"- {d.kind:<9} {d.name}")


def cmd_diag(args, devices):
    lines = [f"RazerLite {__version__} - diagnostic {time.strftime('%Y-%m-%d %H:%M:%S')}",
             f"Python {sys.version.split()[0]} sur {sys.platform}, accès HID : {backend().__name__}",
             "", "Interfaces HID Razer :"]
    for info in enumerate_raw():
        lines.append(f"  {info['product_id']:04x} if={info.get('interface_number')} "
                     f"page={info.get('usage_page', 0):04x} usage={info.get('usage', 0):04x} "
                     f"{info.get('product_string') or ''}")
    lines.append("")
    for d in devices:
        lines.append(f"[{d.name}]")
        checks = [("firmware", d.firmware), ("batterie", d.battery)]
        if d.kind != "headset":
            checks.append(("luminosité", d.brightness))
        if "dpi" in d.spec.features:
            checks += [("dpi", d.dpi), ("paliers", d.dpi_stages), ("fréquence", d.poll_rate), ("veille", d.idle_time),
                       ("molette", d.scroll_settings)]
        if "device_mode" in d.spec.features:
            checks.append(("mode (0 = matériel, 3 = pilote Synapse)", d.device_mode))
        for label, fn in checks:
            try:
                lines.append(f"  {label} : {fn()}")
            except RazerError as exc:
                lines.append(f"  {label} : ERREUR {exc}")
        for req, resp in getattr(d, "log", [])[-6:]:
            lines.append(f"    > {req[:40]}…  < {resp[:40]}…")
        lines.append("")
    text = "\n".join(lines)
    print(text)
    out = Path.cwd() / "razerlite-diag.txt"
    out.write_text(text, encoding="utf-8")
    print(f"Enregistré dans {out}")


def cmd_apply(args, devices):
    config = profiles.load()
    if args.profile:
        if args.profile not in config.get("profiles", {}):
            raise RazerError(f"Profil inconnu : {args.profile}")
        config["active"] = args.profile
        profiles.save(config)
    errors = profiles.apply_profile(devices, profiles.active_profile(config))
    print(f"Profil « {config['active']} » appliqué à {len(devices)} appareil(s).")
    for e in errors:
        print("  !", e)


def cmd_effect(args, devices):
    d = pick(devices, args.device)
    if args.effect == "zones":
        colors = dict(zip(("Molette", "Logo", "Bande"), args.colors or []))
        d.set_zone_colors(colors)
    else:
        d.set_effect(args.effect, zone=args.zone, color1=args.color, color2=args.color2,
                     speed=args.speed, direction=args.direction)
    print("ok")


def cmd_brightness(args, devices):
    pick(devices, args.device).set_brightness(args.percent, zone=args.zone)
    print("ok")


def cmd_dpi(args, devices):
    d = pick(devices, "souris")
    if args.stages:
        stages = [int(x) for x in args.stages.split(",")]
        d.set_dpi_stages(stages, args.active or 1)
        d.set_dpi(stages[(args.active or 1) - 1])
    elif args.value:
        d.set_dpi(args.value)
    print("DPI :", d.dpi(), "| paliers :", d.dpi_stages())


def cmd_poll(args, devices):
    d = pick(devices, "souris")
    d.set_poll_rate(args.hz)
    print("Fréquence :", d.poll_rate(), "Hz")


def cmd_battery(args, devices):
    for d in devices:
        b = d.battery()
        if b:
            print(f"{d.name} : {b[0]} %{' (en charge)' if b[1] else ''}")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="razerlite", description="Remplaçant léger de Razer Synapse")
    parser.add_argument("--tray", action="store_true", help="applique le profil et démarre dans la barre des tâches")
    parser.add_argument("--after-update", action="store_true", help=argparse.SUPPRESS)
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("list", help="liste les appareils reconnus")
    sub.add_parser("diag", help="diagnostic complet (à m'envoyer si ça coince)")
    s = sub.add_parser("apply", help="applique un profil")
    s.add_argument("profile", nargs="?")
    s = sub.add_parser("effect", help="change l'éclairage")
    s.add_argument("device", help="souris, clavier ou casque")
    s.add_argument("effect", choices=["static", "spectrum", "wave", "breathing", "reactive", "starlight", "zones", "off"])
    s.add_argument("--color", default="#00ff88")
    s.add_argument("--color2")
    s.add_argument("--colors", nargs="+", help="pour zones : molette logo bande")
    s.add_argument("--zone")
    s.add_argument("--speed", type=int, default=2)
    s.add_argument("--direction", type=int, default=1)
    s = sub.add_parser("brightness", help="luminosité en %%")
    s.add_argument("device")
    s.add_argument("percent", type=int)
    s.add_argument("--zone")
    s = sub.add_parser("dpi", help="DPI de la souris")
    s.add_argument("value", type=int, nargs="?")
    s.add_argument("--stages", help="ex. 800,1600,3200")
    s.add_argument("--active", type=int)
    s = sub.add_parser("poll", help="fréquence de la souris (125, 500, 1000)")
    s.add_argument("hz", type=int, choices=[125, 500, 1000])
    sub.add_parser("battery", help="niveau des batteries")
    args = parser.parse_args(argv)

    if not args.cmd:
        from .app import run
        return run(start_in_tray=args.tray, after_update=args.after_update)

    handlers = {"list": cmd_list, "diag": cmd_diag, "apply": cmd_apply, "effect": cmd_effect,
                "brightness": cmd_brightness, "dpi": cmd_dpi, "poll": cmd_poll, "battery": cmd_battery}
    devices = []
    try:
        devices = find_devices()
        handlers[args.cmd](args, devices)
    except RazerError as exc:
        print("Erreur :", exc, file=sys.stderr)
        return 1
    finally:
        for d in devices:
            d.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
