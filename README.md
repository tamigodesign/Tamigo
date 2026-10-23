# Tamigo — obaveštaj o pristupačnosti

Lokalni program za pronalaženje **javnih tragova** da ustanova možda treba procenu ili remedijaciju pristupačnosti PDF-a, EPUB-a ili veba.

Program ne donosi pravnu ocenu. Pripadnost sektoru nije dokaz kvara. Svaki lid ima URL izvora, isječak, datum i ograničenje. Ako izvora nema, zapisa nema. Istorijska dodela nikad nije označena kao otvoren poziv.

Proizvod je macOS aplikacija `Tamigo Accessibility Intelligence.app`. Za svakodnevni rad ne treba Cursor, virtuelno okruženje, terminal ni folder repozitorijuma. Baza, podešavanja, istorija pretrage i sačuvani lidovi ostaju u `~/Library/Application Support/TamigoIntel/` i prate nalog, ne `.app` paket. Ažuriranje ili premeštanje aplikacije ih ne briše.

## Kako se dobija aplikacija

Na sopstvenom Macu, iz ovog repozitorijuma:

```bash
bash scripts/build_macos_app.sh
```

Skripta staje sa kodom 2 ako nije macOS. Pravi `dist/Tamigo Accessibility Intelligence.app` i `dist/Tamigo-macos.zip`, pa potpisuje paket ad-hoc potpisom. Nema Apple notarizacije. Pri prvom otvaranju nepotpisane aplikacije koristi se desni klik, pa Open.

Isti tok pokreće GitHub Actions na `macos-14` (`.github/workflows/macos-app.yml`) kad se grana `cursor/accessibility-intelligence-0cba` pošalje. Artefakt je `Tamigo-macos.zip`. Runner je Apple Silicon. Univerzalni binarni paket se ne pravi. Za Intel Mac skripta se pokreće na tom računaru.

Python i `python -m tamigo_intel` ostaju razvojni način. To nije način na koji se program koristi.

## Šta je provereno, a šta nije

Provereno na Linuxu, 23. oktobra 2026: `python3 -m pytest -q` završava sa izlaznim kodom 0 (32 testa). Tu spadaju filter dokaza, oznaka istorijske dodele, čuvanje beleške posle ponovnog otvaranja baze, CanadaBuys parser, i upis `--self-check` / `--stats` i kad proces nema konzolu. Prozor je pokrenut offscreen: lid, ograda i URL izvora se vide. To nije Finder.

`scripts/build_macos_app.sh` na ovom Linuxu staje i ne pravi `.app`. Finder pokretanje nije provereno dok macOS tok u Actions ne prođe, i ni tada dvostruki klik u Finderu nije isti korak kao pokretanje zamrznutog programa iz terminala na runneru. Zamrznuti program na runneru radi `--self-check`, pravu pretragu sa najviše tri ustanove i dva čitanja `--stats`. Tek posle zelenog toka sme da se kaže da je paket startovao na tom Macu.

## Šta je stvarno povezano

| Izvor | Šta radi | Ograničenje |
|---|---|---|
| Contracts Finder (UK) | `POST /api/rest/2/search_notices/json`, ključna reč, pa filter teksta | Samo oglasi koji u naslovu ili opisu imaju jak termin (WCAG, PDF/UA, remediation…). Reč accessibility sama nije dovoljna. |
| USAspending | `POST /api/v2/search/spending_by_award/` | Lid je **naručilac**, ne primalac ugovora. Dodela znači da su ovu vrstu rada već kupili. |
| CanadaBuys | zvanični CSV otvorenih oglasa i najviše dve poslednje fiskalne godine dodela | Lid je naručilac ili navedeni krajnji korisnik, ne dobavljač. Stranica zapisa je `canadabuys.canada.ca`. Nula u iznosu znači da iznos nije objavljen. Starije godine se ne vuku u istom prolazu. |
| TED | `POST https://api.ted.europa.eu/v3/notices/search` | Čuva se naslov i kupac. Tekst oglasa van naslova se ne preuzima. Samo objava mlađa od 45 dana računa se kao moguće otvoren poziv, jer status nije u odgovoru. |
| GitHub issues | javna pretraga issue-a | Nivo C. Vlasnik repozitorijuma nije automatski klijent. |
| SAM.gov | ugrađen poziv | **Ne radi bez API ključa** sa [api.data.gov](https://api.data.gov/). Bez ključa izvor se preskače i to piše u pregledu. |

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

Prioritet podrazumevano: SAD, Kanada, UK, Australija. Niži prioritet, ne zabrana: Srbija i susedi. To se menja u **Podešavanja**. Isključene ustanove se ne upisuju. SAM.gov ključ i GitHub token ostaju samo u lokalnom `config.json`. U dnevniku se prekrivaju.

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
