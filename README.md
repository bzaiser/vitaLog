# vitaLog (Gewicht & Ernährungstracker)

Django-Baukasten-App für Gewichts-, Mahlzeiten-, Wasser- und Aktivitätstracking auf Docker/NAS.

## Enthaltene Baukasten-Kits
- **Basis (geschützt)**: `design_studio`, `ops_kit`
- **Optional (über `/ops/updates/` jederzeit de-/aktivierbar)**: `domain_kit`, `cal_kit`

## NAS Deployment & Updates
Alle Baukasten-Kits liegen persistent im Named Volume `ds_pkg:/opt/ds-pkg` (`PYTHONPATH=/opt/ds-pkg`), dynamisch aktivierte/deaktivierte Kits in `data/installed_kits.json`.

```bash
# Schnelles Update (Git Pull + geänderte Kits nach /opt/ds-pkg + Migrationen + Restart)
./docker/update-fast.sh

# Optionen:
./docker/update-fast.sh --no-kits     # nur App-Code
./docker/update-fast.sh --force-kits  # alle Kits neu nach /opt/ds-pkg
./docker/update-fast.sh --deps        # externe PyPI-Abhängigkeiten neu installieren

# Vollständiger Docker-Image-Rebuild
./docker/update.sh
```
