# Ghid instalare — Tractor Tracker (Termux + Telegram + KMZ)

## 1. Instalare aplicații pe telefonul Samsung

Instalează din **F-Droid** (nu din Play Store — versiunile Termux de pe Play Store sunt vechi și nu mai primesc actualizări):

1. [F-Droid](https://f-droid.org/) — magazinul de aplicații
2. **Termux**
3. **Termux:API**
4. **Termux:Boot**

După instalare, deschide o dată **Termux:Boot** manual (doar ca să confirmi permisiunea "afișare peste alte aplicații" dacă e cerută) — altfel Android nu-i permite să pornească la reboot.

## 2. Permisiuni și setări Samsung / One UI (esențial — a nu se sări)

One UI are mai multe straturi de restricții de fundal peste Android standard, care pot opri silențios scriptul chiar dacă "optimizarea bateriei" pare dezactivată. Aplică toate punctele de mai jos pe **fiecare** din cele 3 aplicații — Termux, Termux:API și Termux:Boot sunt APK-uri separate, fiecare cu propriile restricții.

**2.1 Permisiuni de bază** (Setări → Aplicații → [aplicație]):
- **Locație** (doar Termux/Termux:API) → "Permite tot timpul", nu doar "cât timp folosești aplicația"
- **Notificări** → activate
- **Permisiuni** → dezactivează **"Elimină permisiunile dacă aplicația nu e folosită"** — altfel, dacă tractorul stă nefolosit săptămâni/luni (extrasezon), Android poate revoca singur permisiunea de Locație

**2.2 Baterie** (Setări → Aplicații → [aplicație] → Baterie):
- Setează **"Fără restricții"** — nu doar scoaterea din optimizare; One UI are 3 nivele (Restricționat / Optimizat / Fără restricții) și doar ultimul evită restricțiile agresive de fundal

**2.3 "Put unused apps to sleep"** (Setări → Îngrijirea bateriei și a dispozitivului → Baterie → Limite utilizare fundal):
- Adaugă Termux, Termux:API, Termux:Boot la lista **"Aplicații care nu vor adormi niciodată"**, sau dezactivează complet opțiunea de adormire a aplicațiilor neutilizate
- Verifică listele **"Sleeping apps"** și **"Deep sleeping apps"** — dacă vreuna din cele 3 aplicații apare acolo, scoate-o manual

**2.4 Date de fundal** (Setări → Conexiuni → Utilizare date → Termux):
- Confirmă că **"Permite utilizarea datelor în fundal"** e activ și că Termux nu e restricționat de un mod de economisire date

**2.5 Blocare în Recents**:
- Deschide ecranul de aplicații recente, ține apăsat pe cardul Termux → apasă iconița de lacăt, ca un "închide tot" accidental să nu oprească procesul

**2.6 Economisire energie automată** (Setări → Îngrijirea bateriei → Economisire energie):
- Dezactivează pornirea automată a modului de economisire la un anumit procent baterie — cu alimentare externă + panou solar riscul e mic, dar previne restricții suplimentare de rețea/locație dacă bateria internă scade totuși temporar

## 3. Pachete în Termux

```bash
termux-setup-storage
pkg update && pkg upgrade -y
pkg install python termux-api git -y
pip install requests
```

`termux-setup-storage` cere o permisiune (aprobă) — creează folderul `~/storage/shared/` prin care scriptul scrie arhiva KMZ vizibilă din orice file manager.

## 4. Creare bot Telegram (BotFather)

1. În Telegram, caută **@BotFather** și deschide chat cu el.
2. Trimite `/newbot`, alege un nume și un username (trebuie să se termine în `bot`, ex. `TractorTrackerBot`).
3. BotFather îți dă un **token** de forma `123456789:AAExxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx` — copiază-l.
4. Deschide un chat cu botul tău nou creat și trimite-i orice mesaj (ex. `/start`) — altfel botul nu are cum să-ți afle `chat_id`.

## 5. Aflare `chat_id`

În orice browser (sau `curl`), accesează (înlocuiește `<TOKEN>`):

```
https://api.telegram.org/bot<TOKEN>/getUpdates
```

Caută în răspunsul JSON `"chat":{"id":XXXXXXXXX, ...}` — acel număr e `allowed_chat_id`.

## 6. Copiere cod pe telefon (instalare inițială, tractor nou)

De la v1.26, codul stă într-un repo Git public pe GitHub, ca actualizarea ulterioară a mai multor telefoane (câte un tractor) să nu mai însemne `scp`/`unzip` manual pe fiecare în parte. La instalare inițială:

```bash
cd ~
git clone https://github.com/nicmol81/tractor-tracker.git tractor_tracker
cd tractor_tracker
```

De aici încolo, continuă cu secțiunea 7 (Configurare) — `config.json` și `runtime_config.json` sunt excluse din repo (`.gitignore`), rămân proprii fiecărui telefon și nu sunt niciodată atinse de `git pull`/`/update`.

### Actualizări ulterioare — comanda `/update`

Nu mai e nevoie de SSH pentru actualizări curente de cod. Trimite pur și simplu:
```
/update
```
din Telegram — scriptul face `git pull` în folderul lui, și dacă a apărut cod nou, repornește singur procesul (fără să depindă de bucla de supervizare din secțiunea 15 — folosește `os.execv`, care înlocuiește procesul curent păstrându-i PID-ul). Confirmă apoi cu `/version` că a preluat versiunea nouă. Dacă apare vreo modificare de schemă (chei noi în `runtime_config.json`), acestea se adaugă automat la următoarea pornire, la fel ca înainte (secțiunea 7).

Metoda veche (`scp` + `.zip` prin SSH) rămâne o variantă de rezervă dacă telefonul nu are deloc acces la internet (doar Wi-Fi local spre calculator) — presupune doar copierea fișierelor `.py`/`.md` peste folderul existent, la fel ca înainte de v1.26.

### Migrarea unui telefon instalat cu metoda veche (.zip)

Dacă tractorul a fost instalat înainte de v1.26 (folder `~/tractor_tracker` care nu e un repo Git), o singură dată:

```bash
cd ~/tractor_tracker
pgrep -fl main.py
kill <PID>
cp config.json runtime_config.json /tmp/
cd ~
mv tractor_tracker tractor_tracker.old
git clone https://github.com/nicmol81/tractor-tracker.git tractor_tracker
cp /tmp/config.json /tmp/runtime_config.json tractor_tracker/
rm -rf tractor_tracker.old
cd tractor_tracker
nohup bash install/boot-start-tracker.sh > ~/boot-start-tracker.out 2>&1 & disown
```
Confirmă `/version`, apoi `/update` va funcționa normal la orice actualizare viitoare.

De la v1.3, scriptul se protejează singur împotriva rulării accidentale a două instanțe deodată: dacă pornești manual `python main.py` cât timp altă instanță e deja activă, a doua se oprește imediat și trimite un mesaj Telegram explicativ, în loc să ruleze în paralel.

## 7. Configurare

```bash
cp config.example.json config.json
```

Editează `config.json` (`nano config.json`) și completează `bot_token` și `allowed_chat_id` de mai sus. Fișierul conține și `bot_password` (implicit `"111111"`) — parola pe care trebuie s-o folosească **orice alt cont Telegram** (nu al tău) ca să poată da comenzi botului, prin `/login <parola>`. Contul tău (`allowed_chat_id`) e mereu autorizat automat, fără parolă. Recomandat: schimbă parola implicită cu una mai greu de ghicit înainte să dai acces altcuiva.

Dacă ai deja un `config.json` mai vechi de dinainte de această funcționalitate, adaugă manual linia `"bot_password": "111111"` (sau altă valoare) în el — altfel `/login` nu va reuși pentru nimeni.

Apoi restrânge permisiunile fișierului (conține secrete):

```bash
chmod 600 config.json
```

`runtime_config.json` se creează **automat**, la prima rulare a scriptului, pornind de la valorile implicite din `runtime_config.example.json` (interval mișcare 3 min, staționar 15 min, prag viteză 4 km/h, etc.) — nu trebuie copiat manual. Spre deosebire de `config.json`, care conține secrete, `runtime_config.json` conține setări obișnuite, schimbabile din Telegram cu `/set_moving_interval`, `/set_stationary_interval`, `/set_speed_threshold`, `/rename` etc., sau prin editare manuală.

**Important:** `runtime_config.json` (fișierul live, cu setările tale curente) **nu mai e suprascris de actualizările viitoare** — doar `runtime_config.example.json` (șablonul) face parte din arhivă. La fiecare pornire, scriptul adaugă automat în fișierul tău live doar cheile noi introduse de o versiune mai nouă (dacă există), fără să atingă vreo valoare pe care ai personalizat-o deja (nume tracker, intervale, praguri etc.).

## 8. Test manual, în prim-plan

```bash
python main.py
```

Ar trebui să primești pe Telegram mesajul "Tractor Tracker pornit...". Trimite `/start_rec` din Telegram și urmărește:
- dacă GPS e oprit pe telefon, primești mesajul de avertizare "ATENTIE ! GPS INACTIV..." + o notificare persistentă pe telefon; activează Locația și ar trebui să primești "Locația GPS a fost reactivată."
- apoi primești confirmarea primului punct determinat

Lasă-l să ruleze câteva minute, verifică `/status`, apoi `/stop_rec` — ar trebui să primești fișierul `.kmz` pe Telegram. Deschide-l cu Google Earth sau Google Maps ca să confirmi traseul.

Oprește testul cu `Ctrl+C`.

### Viteza de determinare a poziției (A-GPS)

Scriptul cere poziția prin cereri repetate `termux-location -r once` (una singură, completă, de fiecare dată), nu printr-o sesiune GPS continuă (`-r updates`) — deși a doua variantă părea teoretic mai rapidă, am constatat pe 2026-08-03 un bug confirmat în Termux:API 0.53.0: la a doua actualizare de poziție primită într-o sesiune `-r updates`, aplicația Termux:API crapă intern (`IllegalStateException: JSON must have only one top-level value`, în `LocationAPI.locationToJson`), ceea ce poate întrerupe silențios fluxul de actualizări exact când ai nevoie de mai multe încercări pentru precizie. Cererile `-r once` repetate sunt complet imune la acest bug — fiecare e independentă, produce un singur răspuns JSON complet.

Poți accelera primul fix "la rece" folosind datele de asistență GPS (A-GPS/date de efemeride, exact ce ai văzut în GPS Status ca "assistance data"):
- Instalează o aplicație gen **GPS Status & Toolbox** (F-Droid sau Play Store) și, din meniul ei de gestionare A-GPS, apasă o dată **"Download"/"Reset"** pentru datele de asistență — asta pre-încarcă poziția aproximativă a sateliților, iar primul fix după aceea devine mult mai rapid (secunde, nu minute)
- Datele A-GPS se învechesc după câteva zile — dacă tractorul stă mult nefolosit și semnalul de date e intermitent (cazul tău), primul fix după o pauză lungă poate fi din nou lent până se reîmprospătează automat aceste date; o reîmprospătare manuală ocazională (ex. la începutul sezonului) ajută
- Asigură-te că telefonul are semnal de date (mobil sau WiFi) exact când pornești o înregistrare — asta permite telefonului să descarce datele de asistență proaspete prin rețea, în loc să aștepte recepția lor directă de la sateliți (mult mai lentă)

## 9. Calibrare senzori (obligatoriu de verificat o dată, pe acest telefon)

Formatul exact al răspunsului `termux-location`/`termux-sensor` poate varia ușor între versiuni. Verifică manual:

```bash
termux-location -p gps -r once
```
— confirmă că JSON-ul conține cheile `latitude`, `longitude`, `accuracy`, `speed`. Apoi, cu Locația **dezactivată** din telefon, rulează din nou comanda și notează exact textul de eroare afișat — dacă nu conține „disabled”/„not enabled”/„permission”, ajustează verificarea din [gps.py](gps.py) (`check_gps_enabled`) după cuvintele reale. Această verificare stă la baza avertizării automate GPS-oprit (secțiunea 10).

```bash
termux-sensor -s accelerometer -n 5 -d 200
```
— confirmat pe 2026-08-04: comanda emite **N obiecte JSON separate, concatenate** (câte unul per eșantion, ex. `{"LSM6DSOTR Accelerometer": {"values": [x,y,z]}}`), nu un singur JSON cu un array — [sensors.py](sensors.py) e scris pentru acest format (decodare incrementală, ca la GPS). Dacă vreodată pe alt telefon vezi altă structură, ajustează `_parse_xyz_samples`.

Valori de referință reale (telefon Samsung A53, 2026-08-04):
- **Staționar pe masă**: varianță tipic 0.00001-0.0002, maxim observat 0.00146 — practic zero.
- **Mers cu telefonul în mână** (test pe scări): variază enorm în funcție de intensitate, de la ~0.001 (aproape nemișcat) până la ~20 (zdruncinare puternică), trecând printr-o zonă ambiguă 0.1-4 unde depinde mult de moment.

Pe baza acestor date, pragul implicit a fost coborât la **0.01** (de la 1.5 inițial) — sub orice valoare observată în staționare pură, dar suficient de sensibil să prindă chiar și mișcare ușoară. **Rămâne netestat scenariul motor pornit + tractor nemișcat (ralanti)** — vibrația motorului ar putea produce varianțe peste 0.01 fără nicio deplasare reală. Dacă la testul cu tractorul apar verificări GPS declanșate des în timp ce stă la ralanti (fără să pornească vreodată înregistrarea, datorită filtrului de viteză), crește pragul cu `/set_accel_threshold <valoare>` (sau direct în `runtime_config.json`) până elimină acest fals-pozitiv, păstrându-l totuși sub valorile observate la deplasarea reală.

## 10. Avertizare GPS dezactivat

Un fir de execuție separat verifică periodic (implicit la 180s, `gps_check_interval_s` din `runtime_config.json`) dacă GPS-ul e activ, **indiferent dacă înregistrarea traseului rulează sau nu**. Fiecare verificare lasă o linie `Verificare periodică GPS (watchdog la 180s): activ/oprit` în jurnal — dacă vezi telefonul „căutând poziția" fără să fii pornit `/start_rec`, aceasta e cel mai probabil cauza (comportament normal, necesar pentru avertizarea de mai jos), nu pornirea automată descrisă în secțiunea 13 (care lasă propria ei linie, „Mișcare susținută..."). La dezactivare primești:

- pe Telegram, mesajul: `ATENTIE ! GPS INACTIV. REACTIVATI DETERMINAREA LOCATIEI !` (repetat ca memento la fiecare `gps_alert_repeat_min` minute — implicit 30 — cât timp rămâne oprit, ca să nu ratezi avertizarea dacă nu ai văzut primul mesaj)
- pe telefon, o **notificare persistentă** (nu poate fi înlăturată prin swipe, dispare doar când reactivezi locația), cu prioritate maximă și vibrație, titlul afișat mai mare/bold: „ATENTIE ! GPS INACTIV.” și conținutul „REACTIVATI DETERMINAREA LOCATIEI !”

Când Locația e reactivată, primești pe Telegram „Locația GPS a fost reactivată.” și notificarea de pe telefon dispare automat.

Notă de calibrare: pe unele variante Android/Samsung, notificările cu prioritate „max” apar ca pop-up (heads-up) doar dacă și canalul de notificări al Termux:API are importanța setată la „Urgent”/„Ridicat” din Setări → Aplicații → Termux:API → Notificări — verifică o dată manual acest setaj pe telefon pentru efect maxim de vizibilitate.

Fals-pozitiv la pornirea scriptului (rezolvat): la fiecare pornire, firele `gps_watchdog`, `battery_watchdog` și `auto_start_watchdog` fac fiecare primul apel Termux:API aproape simultan (`termux-location`, `termux-battery-status`, `termux-sensor`) — observat pe telefon: ATENTIE GPS INACTIV imediat la pornire deși locația era activă. Termux:API pare să nu gestioneze bine apeluri concurente și returnează câteodată răspuns gol pentru unul din ele. Fixat prin (a) un lock global (`termux_api.py`) care serializează toate cele trei tipuri de apeluri, indiferent din ce fir vin, și (b) o mică întârziere la pornirea fiecărui fir (5s/10s/15s) ca primele verificări să nu mai coincidă exact.

## 11. Avertizare baterie scăzută

Similar cu avertizarea GPS, un al doilea fir de execuție verifică periodic (implicit la 300s/5 min, `battery_check_interval_s`) procentul bateriei telefonului, indiferent dacă înregistrarea rulează sau nu. Sub `battery_low_threshold_pct` (implicit 20%), primești pe Telegram `LOW BATTERY — baterie telefon din tractor: NN%`, repetat ca memento la fiecare `battery_alert_repeat_min` minute (implicit 30) cât timp rămâne sub prag, apoi o confirmare când urcă din nou peste prag.

Poți verifica oricând starea bateriei la cerere cu `/batt`.

Notă de calibrare: verifică manual `termux-battery-status` (fără argumente) și confirmă că răspunsul conține cheile `percentage` și `plugged` — dacă numele câmpurilor diferă pe acest telefon, ajustează [device.py](device.py) (`get_battery_status`)/[main.py](main.py) (`format_battery_message`, `handle_battery_status`).

Dat fiind că telefonul e alimentat printr-o baterie externă cu panou solar, o scădere sub 20% e un semnal real de problemă (conexiune slăbită, panou acoperit, baterie externă descărcată) — merită tratată ca alertă serioasă, nu ca uzură normală.

## 12. Oprire automată pe timp de noapte (lipsă mișcare)

Dacă tractorul stă parcat noaptea cu înregistrarea încă activă, scriptul o oprește singur ca să nu consume degeaba (deși alimentarea e solară, nu are rost să acumulăm puncte identice ore în șir). Se declanșează doar dacă **toate** condițiile de mai jos sunt adevărate:

- ora locală e în fereastra de noapte (implicit **22:00–06:00**, `night_autostop_start_hour`/`night_autostop_end_hour` — fereastra „înfășoară" peste miezul nopții, deci acoperă tot intervalul, nu doar până la 23:59)
- toate punctele GPS din ultimele `night_autostop_inactivity_min` minute (implicit 60) au viteză sub `speed_threshold_kmh`
- accelerometrul nu a mai detectat nicio mișcare în același interval

Când se declanșează: trimite traseul curent ca fișier KMZ (la fel ca `/stop_rec`) și mesajul pe Telegram:
```
LIPSA MISCARE. INREGISTRAREA A FOST OPRITA
```

Oprirea în sine nu repornește nimic — dar dacă tractorul reintră efectiv în activitate (mișcare susținută + viteză peste prag), pornirea automată descrisă în secțiunea 13 preia și repornește înregistrarea singură, fără să fie nevoie de `/start_rec` manual.

Se poate dezactiva complet (`"night_autostop_enabled": false` în `runtime_config.json`) sau ajusta orele/intervalul de inactivitate editând direct fișierul — nu există încă o comandă Telegram dedicată pentru asta.

## 13. Pornire automată la mișcare

Complementul opririi de noapte: cât timp **nu** e activă nicio înregistrare, un fir de execuție separat monitorizează accelerometrul la fiecare `autostart_check_interval_s` (implicit 60s, reglabil cu `/set_autostart_interval <secunde>`), păstrând o **fereastră glisantă** cu ultimele `autostart_window_size` verificări (implicit 5, deci ~5 minute de istoric, reglabil cu `/set_autostart_window <n>`). Dacă cel puțin `autostart_motion_ratio` din fereastră (implicit 0.6, adică 60% — 3 din 5, reglabil cu `/set_autostart_ratio <0-1>`) arată mișcare, ia un fix GPS.

Toate trei comenzile salvează valoarea imediat în `runtime_config.json` și se aplică din mers, fără repornirea scriptului — firul de monitorizare redimensionează fereastra glisantă la următoarea verificare.

*(Versiunea inițială cerea mișcare la **fiecare** verificare, 10 minute la rând — s-a dovedit nerealist de fragilă: un singur moment de acalmie, ca o oprire la semafor sau o porțiune de drum neted, reseta tot contorul la zero, și practic nu s-a declanșat deloc într-un test real de 3 ore de condus. Fereastra glisantă cu prag procentual tolerează astfel de goluri ocazionale.)*

Fals-pozitiv rezolvat: până la v1.21, pornirea automată apela `begin_session()` direct din firul de monitorizare, care scria sesiunea pe disc dar nu putea seta și variabila internă `recording` din bucla principală — bucla principală rămânea "adormită" la nesfârșit, deci sesiunea exista dar nu se mai înregistra niciun punct, nu se trimitea KMZ la 3h, și nu apărea nicio eroare (diagnosticat dintr-un jurnal real, 2026-08-05: pornire automată reușită la ora 8, apoi zero activitate până seara). Din v1.22, bucla principală își resincronizează starea din `track_store` la fiecare iterație, indiferent din ce fir a pornit sesiunea.

Dacă viteza confirmată la fix e peste `speed_threshold_kmh` (implicit 4 km/h — adică e vorba chiar de deplasarea tractorului, nu doar cineva care s-a urcat în cabină), pornește înregistrarea automat, exact ca și cum ai trimite `/start_rec`, și primești pe Telegram (oră locală):
```
ACCELEROMETRUL A DETECTAT MISCARE. INREGISTRAREA GPS A FOST PORNITA AUTOMAT LA ddmmyy hh.mm.ss
```
urmat de confirmarea obișnuită a primului punct.

Dacă verificarea GPS arată viteză sub prag (mișcare falsă, ex. cineva care umblă prin cabină) sau nu obține fix, fereastra se golește — nu pornește înregistrarea, dar continuă să monitorizeze de la zero.

Se poate dezactiva complet cu `"autostart_enabled": false` în `runtime_config.json`.

**Calibrare pe date reale:** de la această versiune, fiecare verificare a accelerometrului (nu doar cele cu mișcare detectată) e scrisă în jurnal — linia `Accelerometru: varianță=... prag=... -> mișcare/staționar`. După un traseu real, `/getlogfile` îți dă istoricul complet; poți compara varianțele înregistrate în mers față de cele în staționare ca să ajustezi fin `accel_motion_threshold`, `autostart_window_size` și `autostart_motion_ratio` după comportamentul real al acestui telefon în acest vehicul.

## 14. Nume tracker (pentru mai multe tractoare simultan)

Din v1.25, dacă tracker-ul are un nume setat (`/rename`), **fiecare** mesaj trimis de acest tracker pe Telegram — inclusiv comenzi ca `/version`, `/batt`, avertizări, KMZ-uri — începe automat cu `[nume]`, ca să poți distinge ușor de la ce tractor vine fiecare mesaj când ai mai multe active în același chat. Fără nume setat, mesajele pleacă neprefixate ca înainte (de-asta apare avertizarea de la pornire dacă nu ai setat încă un nume).

Dacă ai mai multe telefoane/tractoare care rulează acest script în paralel, fiecare instanță poate avea un nume propriu, ca să știi din numele fișierului KMZ cărui utilaj îi aparține.

- `/name` — afișează numele curent al acestui tracker
- `/rename <nume>` — setează/schimbă numele (poate conține spații, ex. `/rename Tractor Nord`), salvat în `runtime_config.json`

Dacă tracker-ul **nu are nume setat**, primești o avertizare pe Telegram la fiecare pornire a scriptului:
```
ATENTIE: acest tracker nu are un nume setat. Cu mai multe tractoare active simultan,
fișierele KMZ nu vor putea fi identificate ușor. Setează un nume cu /rename <nume>.
```

Numele apare și în confirmarea de la fiecare pornire a scriptului, și în confirmarea de la fiecare pornire a înregistrării (manuală sau automată), ca să știi mereu cu ce tracker interacționezi.

**Numele face parte din fiecare fișier KMZ**, în formatul:
```
[nume tracker] [aallzz] oraSTART [oo.mm.ss].kmz
```
de exemplu `Tractor Nord 260804 oraSTART 08.30.15.kmz` — data și ora sunt **locale** (ora telefonului), nu UTC, chiar dacă intern punctele GPS sunt stocate în UTC. Dacă tracker-ul n-are nume setat, se folosește `FaraNume` în locul numelui. Caractere care nu sunt permise într-un nume de fișier (`\ / : * ? " < > |`) sunt înlocuite automat cu `_`.

## 15. Autostart la pornirea telefonului

```bash
mkdir -p ~/.termux/boot
cp ~/tractor_tracker/install/boot-start-tracker.sh ~/.termux/boot/
chmod +x ~/.termux/boot/boot-start-tracker.sh
```

Repornește telefonul o dată ca test și confirmă (de exemplu prin `/status` din Telegram, sau verificând `~/tractor_tracker/tractor_tracker.log`) că scriptul a pornit singur.

## 16. Comenzi Telegram disponibile

| Comandă | Efect |
|---|---|
| `/start_rec` | pornește înregistrarea traseului |
| `/stop_rec` | oprește, trimite KMZ-ul curent, arhivează local |
| `/status` | poziție GPS instantanee, fără să aștepți cele 3 ore |
| `/map` | link Google Maps către poziția curentă |
| `/rec_status` | spune dacă înregistrarea e activă acum, de câte minute și câte puncte are |
| `/name` | numele curent al acestui tracker |
| `/rename <nume>` | schimbă numele acestui tracker (apare în fișierele KMZ) |
| `/batt` | starea bateriei telefonului din tractor (procent + încărcare) |
| `/version` | versiunea codului care rulează pe telefon chiar acum |
| `/update` | descarcă ultima versiune din Git (`git pull`) și repornește scriptul singur |
| `/description` | explică fluxul de funcționare, cu setările active (intervale, praguri) |
| `/getlogfile` | trimite pe Telegram fișierul de log curent, util la depanare |
| `/set_moving_interval <min>` | interval de logare când tractorul se mișcă (implicit 3) |
| `/set_stationary_interval <min>` | interval de logare când tractorul stă (implicit 15) |
| `/set_speed_threshold <kmh>` | pragul de viteză mișcare/staționar (implicit 4) |
| `/set_accel_threshold <valoare>` | pragul de sensibilitate al accelerometrului (implicit 0.01) |
| `/set_autostart_interval <secunde>` | cât de des verifică accelerometrul cât timp înregistrarea e oprită (implicit 60) |
| `/set_autostart_window <n>` | câte verificări intră în fereastra de pornire automată (implicit 5) |
| `/set_autostart_ratio <0-1>` | ce procent din fereastră trebuie să arate mișcare (implicit 0.6 = 60%) |
| `/login <parola>` | autorizează chat-ul curent să folosească botul (necesar doar pentru alte conturi decât al tău) |
| `/help` | recapitulare comenzi |

Comenzile nu sunt case-sensitive — `/getLOGfile` funcționează la fel ca `/getlogfile`.

### Control acces (parolă)

Contul din `allowed_chat_id` (al tău) e mereu autorizat, fără parolă. Orice alt cont Telegram care scrie botului trebuie să trimită întâi `/login <parola>` (parola din `bot_password`, `config.json`) — până atunci, orice altă comandă primește răspunsul „Acces neautorizat. Trimite /login <parola>." Odată autorizat, un chat rămâne autorizat cât timp scriptul rulează neîntrerupt; **la fiecare repornire a scriptului (inclusiv update de cod), conturile suplimentare trebuie să dea din nou `/login`** — doar contul tău din `config.json` e mereu autorizat automat.

Notă de securitate: parola implicită `111111` e doar pentru pornire rapidă — schimb-o în `config.json` înainte să dai acces cuiva. Comunicarea prin Telegram nu e end-to-end criptată către bot (Telegram vede conținutul mesajelor pe server), deci nu folosi aici o parolă pe care o refolosești și în alte conturi importante.

## 17. Jurnal (log) și depanare

Scriptul scrie continuu un jurnal în `~/tractor_tracker/tractor_tracker.log` (fix-uri GPS obținute/eșuate, mișcare detectată de accelerometru, comenzi primite, sesiuni pornite/finalizate, eșecuri de trimitere pe Telegram, erori neașteptate). Fișierul are rotație automată (max ~2MB, păstrează 3 fișiere vechi `.log.1`, `.log.2`, `.log.3`), deci nu umple stocarea telefonului.

Cel mai simplu mod de a-l consulta e să trimiți `/getlogfile` din Telegram — primești fișierul curent ca document, inclusiv dacă tractorul e departe și nu ai acces fizic la telefon. Dacă e nevoie de istoricul mai vechi (fișierele `.log.1` etc.), acestea rămân doar local pe telefon, în `~/tractor_tracker/`.

Există și un fișier separat `~/tractor_tracker/startup_errors.log`, folosit doar ca plasă de siguranță pentru erori apărute înainte ca jurnalul principal să apuce să pornească (ex. o dependință Python lipsă) — se golește automat la fiecare repornire a telefonului. **Necesită bucla de supervizare activă** (secțiunea 15/20) ca să fie util — dacă scriptul rulează pornit direct cu `python main.py` (fără `boot-start-tracker.sh`), acest fișier nu se mai completează deloc.

Din v1.24, fiecare fir de fundal (`gps_watchdog`, `battery_watchdog`, `auto_start_watchdog`, `telegram_listener`) prinde orice eroare neașteptată, o scrie complet în `tractor_tracker.log` (deci vizibilă prin `/getlogfile`, nu doar în `startup_errors.log`) și continuă bucla, în loc să moară silențios. Înainte de v1.24, o eroare necaptată într-un fir de fundal îl omora definitiv până la următoarea repornire a procesului, fără nicio urmă în jurnal dacă supervisorul nu era activ (exact ce s-a întâmplat cu `gps_watchdog` pe 4 august — vezi `device.clear_gps_alert`).

## 18. Arhivă locală

Fiecare fișier `.kmz` trimis cu succes pe Telegram rămâne salvat și în `~/storage/shared/TractorTracks/`, vizibil din orice file manager Android sau prin cablu la calculator.

## 19. Checklist final

- [ ] Termux, Termux:API, Termux:Boot instalate din F-Droid
- [ ] Pentru toate cele 3 aplicații: Baterie "Fără restricții", excluse din "put unused apps to sleep"/"sleeping apps", "elimină permisiuni neutilizate" dezactivat, date de fundal permise, blocate în Recents (secțiunea 2)
- [ ] Locație "Permite tot timpul", notificări active
- [ ] `config.json` completat cu token și chat_id corecte, `chmod 600`
- [ ] Test manual `/start_rec` → puncte acumulate → `/stop_rec` → KMZ primit și verificat în Google Earth
- [ ] Calibrare `check_gps_enabled` și `accel_motion_threshold` pe acest telefon anume
- [ ] Test motor pornit + tractor nemișcat (ralanti) — confirmă că `accel_motion_threshold=0.01` nu produce verificări GPS false-pozitive din vibrația motorului; dacă apar des, crește pragul cu `/set_accel_threshold`
- [ ] `boot-start-tracker.sh` copiat în `~/.termux/boot/`, testat cu un restart real al telefonului
- [ ] Verificare comportament cu semnal intermitent: oprește temporar datele mobile în timpul unei sesiuni active, confirmă că scriptul continuă să înregistreze punctele local și trimite KMZ-ul (din coada de reîncercare) când revine semnalul
- [ ] Test `/getlogfile` — confirmă că primești fișierul de log pe Telegram
- [ ] Test avertizare GPS: dezactivează Locația **fără** să fii într-o sesiune de înregistrare — confirmă mesajul Telegram + notificarea persistentă pe telefon; reactivează — confirmă mesajul de reactivare și dispariția notificării
- [ ] Test `/batt` — confirmă procentul afișat și starea de încărcare corespund realității telefonului
- [ ] Test avertizare baterie scăzută (poți coborî temporar `battery_low_threshold_pct` peste procentul curent real al telefonului, ca să declanșezi imediat alerta fără să aștepți descărcarea efectivă)
- [ ] `config.json` conține și `bot_password`, schimbată din valoarea implicită `111111`
- [ ] Test control acces: de pe alt cont Telegram (nu al tău), trimite o comandă (ex. `/status`) — confirmă "Acces neautorizat"; trimite `/login <parola>` — confirmă autorizarea; reîncearcă comanda — confirmă că funcționează acum
- [ ] Test oprire automată de noapte: setează temporar în `runtime_config.json` `night_autostop_start_hour`/`night_autostop_end_hour` ca să acopere ora curentă și `night_autostop_inactivity_min` la o valoare mică (ex. 2), pornește `/start_rec`, lasă telefonul nemișcat — confirmă că după intervalul respectiv primești KMZ-ul + mesajul „LIPSA MISCARE...”; repune apoi valorile reale (22/6/60)
- [ ] Test pornire automată: cu `/stop_rec` dat (fără înregistrare activă), coboară temporar `autostart_window_size` la o valoare mică (ex. 3) ca să nu aștepți ~7.5 minute, mișcă/scutură telefonul intermitent (nu neapărat perfect continuu, testează exact toleranța la goluri), apoi deplasează-te (sau simulează viteză) — confirmă mesajul „Pornire automată...” și că înregistrarea chiar a pornit (`/rec_status`); repune apoi valoarea reală (15). Ideal, repetă și testul real de condus (ca cel din 2026-08-04) ca să confirmi că acum se declanșează.
- [ ] Test nume tracker: repornește scriptul fără nume setat — confirmă avertizarea Telegram; trimite `/rename Test`, confirmă cu `/name`; pornește o înregistrare scurtă și `/stop_rec` — confirmă că fișierul KMZ primit se numește `Test AALLZZ oraSTART OO.MM.SS.kmz` cu ora locală corectă (nu UTC)
