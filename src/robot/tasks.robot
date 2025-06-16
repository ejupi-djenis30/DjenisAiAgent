*** Settings ***
Library    LinuxAgent.py

*** Test Cases ***
Cerca Volo Economico
    Execute Task On UI    Trova il volo più economico da Roma a Tokyo per martedì prossimo e fermati prima di confermare il pagamento.

Organizza File Nella Scrivania
    Execute Task On UI    Apri la cartella 'Documenti', crea una nuova cartella chiamata 'Fatture 2024' e sposta tutti i file PDF in quella cartella.

Controlla Meteo
    Execute Task On UI    Apri il browser web, vai su un sito di meteo e cerca le previsioni per domani a Milano. Scrivi il risultato in un file di testo sulla Scrivania.
