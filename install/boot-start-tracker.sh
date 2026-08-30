#!/data/data/com.termux/files/usr/bin/sh
# Pus in ~/.termux/boot/ (Termux:Boot) -- porneste automat la reboot si
# repune scriptul in functiune daca acesta se opreste dintr-un motiv oarecare.
#
# Jurnalul normal de functionare e scris chiar de main.py in tractor_tracker.log
# (cu rotatie, accesibil si prin comanda Telegram /getlogfile). Fisierul de mai
# jos e doar o plasa de siguranta pentru erori aparute inainte ca logging-ul
# din Python sa apuce sa porneasca (ex. dependinta lipsa) -- se goleste la
# fiecare repornire a telefonului ca sa nu creasca nelimitat.

termux-wake-lock

cd ~/tractor_tracker || exit 1
: > startup_errors.log

while true; do
  python main.py >> startup_errors.log 2>&1
  sleep 5
done
