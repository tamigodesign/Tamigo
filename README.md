# Tamigo — obaveštaj o pristupačnosti

Lokalni program za pronalaženje **javnih tragova** da ustanova možda treba procenu ili remedijaciju pristupačnosti PDF-a, EPUB-a ili veba.

Program ne donosi pravnu ocenu. Pripadnost sektoru nije dokaz kvara. Svaki lid ima URL izvora, isječak, datum i ograničenje. Ako izvora nema, zapisa nema. Istorijska dodela nikad nije označena kao otvoren poziv.

Proizvod je macOS aplikacija `Tamigo Accessibility Intelligence.app`. Za svakodnevni rad ne treba Cursor, virtuelno okruženje, terminal ni folder repozitorijuma. Baza, podešavanja, istorija pretrage i sačuvani lidovi ostaju u `~/Library/Application Support/TamigoIntel/` i prate nalog, ne `.app` paket. Ažuriranje ili premeštanje aplikacije ih ne briše.

## Kako se dobija aplikacija

Računar za ovaj proizvod je Intel Mac na macOS Sequoia. Paket za njega je artefakt **Tamigo-macos-intel**. Apple Silicon arhiva **Tamigo-macos-apple-silicon** postoji posebno i nije paket za taj računar.

Na Intel Macu, iz ovog repozitorijuma, sa Pythonom 3.12 (instalacija sa python.org ako `python3` nije već tu):

```bash
bash scripts/build_macos_app.sh
```

Skripta staje sa kodom 2 ako nije macOS. Na Intelu pravi `dist/Tamigo Accessibility Intelligence.app` i `dist/Tamigo-macos-intel.zip`. Na Apple Siliconu ime arhive je `dist/Tamigo-macos-apple-silicon.zip`. Potpis je ad-hoc. Nema Apple notarizacije. Pri prvom otvaranju nepotpisane aplikacije koristi se desni klik, pa Open.

Isti tok pokreće GitHub Actions (`.github/workflows/macos-app.yml`). Intel posao ide na `macos-15-intel`. Apple Silicon posao ostaje na `macos-14`. Pre pakovanja skripta proverava da su Python i PySide6 te arhitekture, a posle pakovanja da Mach-O fajlovi u `.app` nose istu arhitekturu.

Python i `python -m tamigo_intel` ostaju razvojni način. To nije način na koji se program koristi.

## Šta je provereno, a šta nije

Lokalni pytest posle izbora zemlje, klasa grešaka i Find a Tender završio je sa 55 tačaka i izlaznim kodom 0. Prozor je offscreen. To nije Finder. Ranija provera na Linuxu, 24. oktobra 2026. oko 03:26 po beogradskom vremenu, imala je 44 testa i pokrivala je period od 90 dana, osvežavanje, čišćenje prikaza, potvrdu brisanja, izostanak API ključa iz config.json, dnevnika i izvoza, neuspeh, delimičan ishod, istoriju dokaza, CanadaBuys parser i `--self-check` / `--stats`. `scripts/build_macos_app.sh` na Linuxu staje i ne pravi `.app`.

Trenutni Intel paket, sa izborom zemlje i Find a Tender, proveren je na GitHub runneru `macos-15-intel`, 24. oktobra 2026. Posao `Tamigo-macos-intel` završen je u 04:43 po beogradskom vremenu: [Actions run 40054890770](https://github.com/tamigodesign/Tamigo/actions/runs/40054890770). Runner javlja macOS 15.7.9 (24G830) i `Intel(R) Core(TM) i7-8700B CPU @ 3.20GHz`. `uname` je `x86_64`. Python 3.12.10 je `x86_64`. Na tom runneru `python -m pytest -q` daje 55 tačaka i korak se završava uspešno. Pre pakovanja provereno je 403 PySide6 Mach-O fajla. U `.app` je provereno 1138 Mach-O fajlova i svi nose `x86_64`. Glavni program je `Mach-O 64-bit executable x86_64`. PyInstaller je SDK spustio sa 26.2.0 na 12.1.0, u skladu sa Python bibliotekom. Zamrznuti program je prijavio verziju 0.2.0, `frozen: true`, `platform: darwin`, `machine: x86_64`. Prava pretraga, sa granicom od 3 ustanove, sačuvala je DSIT, Department for Business and Trade i MCA - Maritime and Coastguard Agency. Contracts Finder je odgovorio sa 8 zapisa, sačuvao 3 ustanove, i nijedna nije odbačena zbog zemlje (`van izabranih zemalja 0`, filter zemlje je podrazumevano isključen). Ishod je `completed_with_results`. Find a Tender u tom prolazu nije bio izvor: podrazumevano je isključen, a ostali izvori nisu pitani jer je maksimum dostignut. To nije zabeleženo kao neuspeh. Pretraga unutar zamrznutog programa završena je u 04:42 po beogradskom vremenu. Drugo čitanje statistike i dalje vidi 3 ustanove, 3 lida, nivo A ili B: 3, otvorena nabavka: 0, čeka proveru: 3, zemlja GB, kategorije vlada 2 i nije utvrđeno 1. Artefakt je **Tamigo-macos-intel** (265.902.513 bajtova): https://github.com/tamigodesign/Tamigo/actions/runs/40054890770/artifacts/12545285904

Taj Intel paket nema raspored u kome je izbor zemlje na vrhu kartice Pretraga, niti BOAMP. Ti delovi stižu u sledećem Intel paketu, kad prolaz za taj commit završi. Ovaj zapis ne tvrdi da je taj noviji paket već spreman.

To pokretanje je išlo naredbom na binarni fajl unutar `.app`, na tuđem Intel Macu u Actions. Dvostruki klik u Finderu na tvom računaru nije rađen. Potpis je ad-hoc. Nema notarizacije. Pri prvom otvaranju: desni klik, pa Open. Stariji artefakt iz [prolaza 40049894632](https://github.com/tamigodesign/Tamigo/actions/runs/40049894632/artifacts/12543061819) (03:35 po beogradskom vremenu, 265.887.837 bajtova) ima ispravke perioda, ishoda, Keychain-a i sertifikata, ali nema izbor zemlje ni Find a Tender. Još stariji [prolaz 40024868133](https://github.com/tamigodesign/Tamigo/actions/runs/40024868133) nema ni te ispravke.

Apple Silicon arhiva **Tamigo-macos-apple-silicon** iz istog prolaza (237.510.823 bajtova) nije paket za Intel Mac. Starije ime `Tamigo-macos.zip` je bilo samo za Apple Silicon i više se ne koristi. AusTender i dalje vraća 403 i nije povezan.

## Šta je stvarno povezano

| Izvor | Šta radi | Ograničenje |
|---|---|---|
| Contracts Finder (UK) | `POST /api/rest/2/search_notices/json`, ključna reč, pa filter teksta | Samo oglasi koji u naslovu ili opisu imaju jak termin (WCAG, PDF/UA, remediation…). Reč accessibility sama nije dovoljna. |
| USAspending | `POST /api/v2/search/spending_by_award/` | Lid je **naručilac**, ne primalac ugovora. Dodela znači da su ovu vrstu rada već kupili. |
| CanadaBuys | zvanični CSV otvorenih oglasa i najviše dve poslednje fiskalne godine dodela | Lid je naručilac ili navedeni krajnji korisnik, ne dobavljač. Stranica zapisa je `canadabuys.canada.ca`. Nula u iznosu znači da iznos nije objavljen. Starije godine se ne vuku u istom prolazu. |
| TED | `POST https://api.ted.europa.eu/v3/notices/search` | Čuva se naslov i kupac. Tekst oglasa van naslova se ne preuzima. Samo objava mlađa od 45 dana računa se kao moguće otvoren poziv, jer status nije u odgovoru. |
| GitHub issues | javna pretraga issue-a | Nivo C. Vlasnik repozitorijuma nije automatski klijent. Nije izvor za jednu zemlju. |
| SAM.gov | ugrađen poziv | **Ne radi bez API ključa** sa [api.data.gov](https://api.data.gov/). Bez ključa izvor se preskače i to piše u pregledu. |
| Find a Tender (UK) | zvanični OCDS `ocdsReleasePackages` | Podrazumevano isključen. Čitaju se najnovija izdanja, najviše četiri stranice, pa lokalni filter. Nije pretraga cele arhive. HTML oglasa sa ove mreže 24. oktobra 2026. vraća HTTP 403. API je iste večeri vratio HTTP 200. 403 ovde nije greška sertifikata. |
| BOAMP (Francuska) | Open Data DILA, pretraga predmeta oglasa | Podrazumevano isključen. Ključ nije potreban. Najviše četiri reči i dvadeset zapisa po reči. Ceo tekst oglasa se ne preuzima. Dodela nije otvoren poziv. Nije cela francuska nabavka. Živa proba 24. oktobra 2026. vratila je HTTP 200. |

Izbor zemlje je odvojen od izbora izvora. Filter zemlje je podrazumevano isključen, pa se i dalje čuvaju sve zemlje koje izvor vrati. Uključivanje filtera ne briše stare zapise. Višejezične fraze se dodaju samo kad se to uključi. Nacionalni portali (bund.de, TenderNed, BOAMP, ANAC, ANKÖ, udbud.dk, HILMA, simap.ch, e-JN, eTenders, AusTender) nisu povezani. CanadaBuys otvoreni CSV je 24. oktobra 2026. posle 04:30 po beogradskom vremenu sa ove mreže vratio HTTP 200 i zaglavlje CSV-a.

Kanada, primer iz fajla dodela 2026–2027, pročitan 23. oktobra 2026. Oba su istorijske dodele, ne otvoreni pozivi:

- Department of Natural Resources (NRCan), stojna ponuda za izradu pristupačnih PDF-ova. https://canadabuys.canada.ca/en/tender-opportunities/award-notice/cb-748-24542208
- Department of Fisheries and Oceans (DFO), naslov ACCESSIBILITY TESTING, iznos 45200 CAD. https://canadabuys.canada.ca/en/tender-opportunities/award-notice/cb-50-75070499

Imejl iz kolone kontakta u tom CSV-u upisuje se samo ako je stvarno u redu, sa statusom `published_in_source`.

AusTender OCDS adresa `https://api.tenders.gov.au/ocds/findByDates/...` sa ove mašine vraća HTTP 403 `MissingAuthenticationTokenException`. Australijski portal zato nije povezan. Nisu ugrađeni ni axe-core, Playwright, veraPDF, PAC, EPUBCheck ni DAISY Ace. PDF se gleda preko pypdf (oznaka tagovanja, `/Lang`, naslov, tekst prve strane). EPUB se gleda kao ZIP (mimetype, jezik, nav, alt, a11y metapodaci). HTML provera je lokalni parser, bez kontrasta i bez testa tastature. Automatski indikator nije potvrda neusklađenosti, a prazan rezultat nije potvrda usklađenosti.

## Pokretanje iz repozitorijuma

Ovo je razvoj, ne instalirana aplikacija. Potreban je Python 3.11 ili noviji.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m tamigo_intel
```

Baza i podešavanja stoje u `~/Library/Application Support/TamigoIntel/`. Na Linuxu je to `~/.local/share/tamigo-intel/`. Promenljiva `TAMIGO_INTEL_HOME` preusmerava taj folder. On se ne šalje na GitHub.

Pretraga iz terminala, bez prozora:

```bash
python -m tamigo_intel --search --max-organizations 15
python -m tamigo_intel --export json --qualified-only --output lidovi.json
python -m tamigo_intel --export csv --output lidovi.csv
```

## Period, osvežavanje i brisanje

Podrazumevani period unazad je **90 dana**. Polje prima ceo broj od **1** do **7300**. Duži broj i dalje uključuje starije oglase. Kraći period ostavlja već sačuvane zapise u bazi. Ako je u `config.json` ostao stari podrazumevani period od 1825 dana, program ga jednom prebacuje na 90. Posle toga izabrani broj, uključujući 1825 ili 1845, ostaje.

**Pokreni pretragu** i **Osveži / ponovi pretragu** pitaju uključene izvore i spajaju nalaze sa postojećim zapisima. Beleške, dokazi, ustanove i istorija pretrage ostaju. **Zaustavi pretragu** prekida tekući prolaz. **Ažuriraj brojače** samo ponovo čita brojeve i ne pokreće izvore.

**Očisti trenutni prikaz** skida redove sa ekrana. Baza ostaje. **Obriši izabrane zapise** i **Obriši sve lokalne istraživačke podatke** traže potvrdu, podrazumevani odgovor je Ne, i pre brisanja prave `backups/pre-brisanja-….sqlite`. Brisanje svega ostavlja sačuvane pretrage, podešavanja i ključeve.

Iznad kartica piše vreme poslednjeg prolaza u kome je bar jedan izvor odgovorio i ishod poslednjeg pokretanja. Ishodi su: završeno sa sačuvanim tragovima, uspešno bez sačuvanih tragova, delimično, neuspeh, zaustavljeno, greška, i čeka podešavanje kad nijedan uključeni izvor nije mogao da se pozove. Tabela na kartici Pretraga pokazuje ishod, broj odgovora i detalj po izvoru. Prolaz u kome nijedan uključeni izvor nije odgovorio označen je kao neuspeh.

Provera TLS sertifikata ostaje uključena. Spakovani program koristi paket sertifikata iz `certifi`.

## Kako se radi sa lidom

1. U **Pretraga** ostavite izvore koji vam trebaju i pokrenite. Zaustavljanje čuva već upisane redove.
2. U **Lidovi** filtrirajte nivo. A znači da je pristupačnost predmet oglasa ili uvod opisa. Ako se WCAG pojavi tek kao sporedan uslov, nivo je C. B je automatski indikator na fajlu. C obuhvata i GitHub. D bez dokaza se ne pravi.
3. Otvorite izvorni link i pročitajte oglas. Bodovi ne zamenjuju taj korak.
4. Imejl postoji samo ako je prepisan iz teksta izvora i označen je sa `published_in_source`. Program ne izmišlja adrese. `unverified` nikad ne postaje `verified` u izvozu.
5. PDF, EPUB ili HTML možete proveriti dugmetom **Analiziraj fajl** na izabranom lidu. Prazan rezultat ne znači da je dokument usklađen.
6. Kad ručno proverite, stavite status i belešku. Nova pretraga tu proveru ne briše.
7. Izvezite CSV (UTF-8 sa BOM, da ga Excel otvori) ili JSON. Kvalifikovani izvoz drži samo nivo A i B koji nisu odbačeni.

Pravni linkovi u detalju su podsetnik za proveru. Ne ulaze u bodove i ne tvrde da se zakon primenjuje na tu ustanovu.

## Podešavanja

Prioritet podrazumevano: SAD, Kanada, UK, Australija. Niži prioritet, ne zabrana: Srbija i susedi. To se menja u **Podešavanja i API ključevi**. Isključene ustanove se ne upisuju.

Za svaki izvor piše da li je ključ obavezan, opcion ili nepotreban, da li je sačuvan, zvanična adresa za dobijanje pristupa i poznato ograničenje. SAM.gov traži ključ sa [api.data.gov/signup](https://api.data.gov/signup/). Dokumentacija je na [open.gsa.gov](https://open.gsa.gov/api/get-opportunities-public-api/). GitHub token je opcion i pravi se na [github.com/settings/tokens](https://github.com/settings/tokens). Lozinka naloga se ne traži. **Proveri vezu** šalje kratak zahtev i ostavlja poslednji ishod.

Na macOS ključ ide u Keychain, servis `Tamigo Accessibility Intelligence`. `config.json` dobija prazno polje. Prazno polje pri čuvanju ostavlja sačuvani ključ. **Ukloni sačuvani ključ** ga skida posle potvrde. Ključ se ne upisuje u dnevnik ni u izvoz lidova.

Rezervna kopija baze pravi se dugmetom u podešavanjima (`backups/tamigo-backup.sqlite`).

Zakazano ponavljanje **ne radi** kad je program zatvoren. Nema pozadinske usluge.

## Testovi

```bash
pip install -r requirements.txt
python -m pytest -q
```

Na Linuxu za prozor treba Qt biblioteke (`libegl1` i prateće). Na macOS ih donosi PySide6. Posle pytest-a proces se namerno gasi pre Qt rušenja pri isključivanju interpretera, pa se sažetak „N passed“ ne ispisuje. Izlazni kod ostaje onaj koji je pytest izračunao.

## Čega program namerno nema

- Nema slanja poruka ustanovama.
- Nema obilaska iza prijave, CAPTCHA ili zabrane u `robots.txt`.
- Nema tvrdnje da je pokriven ceo svet.
- Nema tvrdnje da visok skor znači budžet ili nameru da kupe uslugu.
- LLM rezime nije uključen. Rezime sklapa pravilo iz sačuvanih isječaka. Tvrdnja bez `evidence_id` ne može ostati potvrđena.
