# Tamigo — obaveštaj o pristupačnosti

Lokalni program za pronalaženje **javnih tragova** da ustanova možda treba procenu ili remedijaciju pristupačnosti PDF-a, EPUB-a ili veba.

Program ne donosi pravnu ocenu. Pripadnost sektoru nije dokaz kvara. Svaki lid ima URL izvora, isječak, datum i ograničenje. Ako izvora nema, zapisa nema.

## Šta je stvarno povezano

| Izvor | Šta radi | Ograničenje |
|---|---|---|
| Contracts Finder (UK) | `POST /api/rest/2/search_notices/json`, ključna reč, pa filter teksta | Samo oglasi koji u naslovu ili opisu imaju jak termin (WCAG, PDF/UA, remediation…). Reč accessibility sama nije dovoljna. |
| USAspending | `POST /api/v2/search/spending_by_award/` | Lid je **naručilac**, ne primalac ugovora. Dodela znači da su ovu vrstu rada već kupili. |
| TED | `POST https://api.ted.europa.eu/v3/notices/search` | Čuva se naslov i kupac. Tekst oglasa van naslova se ne preuzima. Samo objava mlađa od 45 dana računa se kao moguće otvoren poziv, jer status nije u odgovoru. |
| GitHub issues | javna pretraga issue-a | Nivo C. Vlasnik repozitorijuma nije automatski klijent. |
| SAM.gov | ugrađen poziv | **Ne radi bez API ključa** sa [api.data.gov](https://api.data.gov/). Bez ključa izvor se preskače i to piše u pregledu. |

Nisu ugrađeni, jer nisu provereni kao slobodan i pouzdan pristup u ovom okruženju: axe-core, Playwright, veraPDF, PAC, EPUBCheck, DAISY Ace, kanadski i australijski portali nabavki. PDF se gleda preko pypdf (oznaka tagovanja, `/Lang`, naslov, tekst prve strane). EPUB se gleda kao ZIP (mimetype, jezik, nav, alt, a11y metapodaci). HTML provera je lokalni parser, bez kontrasta i bez testa tastature.

## Pokretanje na macOS

Potreban je Python 3.11 ili noviji.

```bash
cd putanja/do/Tamigo
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m tamigo_intel
```

Baza i podešavanja stoje u `~/Library/Application Support/TamigoIntel/`. Na Linuxu je to `~/.local/share/tamigo-intel/`. Taj folder se ne šalje na GitHub.

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

Na Linuxu za prozor treba Qt biblioteke (`libegl1` i prateće). Na macOS ih donosi PySide6.

## Čega program namerno nema

- Nema slanja poruka ustanovama.
- Nema obilaska iza prijave, CAPTCHA ili zabrane u `robots.txt`.
- Nema tvrdnje da je pokriven ceo svet.
- Nema tvrdnje da visok skor znači budžet ili nameru da kupe uslugu.
- LLM rezime nije uključen. Rezime sklapa pravilo iz sačuvanih isječaka. Tvrdnja bez `evidence_id` ne može ostati potvrđena.
