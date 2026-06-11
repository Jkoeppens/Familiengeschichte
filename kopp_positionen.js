// ═══════════════════════════════════════════════════════════
// KOPP — Positionstabelle Hans-Jürgen Koppermann
//
// status-Werte:
//   'belegt'    — WASt-Dokument oder Bundesarchiv-Schreiben, Ort sicher
//   'einheit'   — Einheitsstandort nach Tessin Bd.4, Koppermann vermutlich dabei
//   'unbekannt' — Keine individuelle Meldung, Einheit als Proxy (unsicher)
//   'lazarett'  — WASt-Karte I belegt, Ort und Datum sicher
//   'verwundet' — WASt-Karte I, exakter Ort und Datum belegt
//   'vermisst'  — WASt-Karte II, 13.01.1945 belegt
//
// quelle-Werte:
//   'wast_I'         — WASt-Karte I (B 563-1 KARTEI/K-1458/033)
//   'wast_II'        — WASt-Karte II
//   'bundesarchiv'   — Bundesarchiv-Schreiben PA 2 2021/G-12837
//   'tessin'         — Tessin, Verbände und Truppen Bd. 4 (Einheitsebene)
//   'keine'          — Kein Einzelnachweis
// ═══════════════════════════════════════════════════════════

const KOPP = {

  // ── 1939 ──────────────────────────────────────────────────
  // Bundesarchiv-Schreiben: "1. Kp. N.A. 20 gemeldet: 1939"
  // Polenfeldzug ist Sept.–Okt. 1939, dann Westfront-Aufmarsch.
  // Wo genau in Polen: nicht dokumentiert, Einheitsebene.
  '1939-09': {
    lat: 52.8, lon: 21.5,
    ort: 'Polen — Narew (Einheitsstandort N.A. 20)',
    einheit: 'N.A. 20 / 20. Inf.Div.(mot.)',
    status: 'einheit',
    quelle: 'bundesarchiv',
    popup_hinweis: 'Bundesarchiv belegt N.A. 20 für 1939. Genaue Position innerhalb Polens nicht dokumentiert — Einheitsstandort als Näherung.'
  },
  '1939-10': {
    lat: 52.8, lon: 21.5,
    ort: 'Polen — Narew (Einheitsstandort, Kriegsende Polen 06.10.1939)',
    einheit: 'N.A. 20 / 20. Inf.Div.(mot.)',
    status: 'einheit',
    quelle: 'tessin',
    popup_hinweis: 'Kein individueller Nachweis. Division nach Polenfeldzug in Westverlegung.'
  },

  // ── 1939-11 bis 1941-05: KEINE INDIVIDUELLE MELDUNG ──────
  // Das Bundesarchiv-Schreiben nennt für 1940 und 1941 KEINE
  // Einheitenmeldung für Koppermann. Nächster Eintrag ist 1942.
  // Division war laut Tessin: Westfeldzug Mai-Jun 1940,
  // dann Besatzung Frankreich bis Apr 1941, dann Ostfront ab Jun 1941.
  // Koppermanns individueller Verbleib in dieser Phase: UNBEKANNT.

  '1939-11': {
    lat: 50.3, lon: 6.5,
    ort: 'Eifel / Westwall-Aufmarsch (Einheitsstandort)',
    einheit: 'N.A. 20 / 20. Inf.Div.(mot.)',
    status: 'unbekannt',
    quelle: 'keine',
    popup_hinweis: 'KEIN individueller Nachweis für diesen Zeitraum. Das Bundesarchiv-Schreiben nennt für 1940–1941 keine Einheitenmeldung für Koppermann. Gezeigt wird der Einheitsstandort nach Tessin als Näherung.'
  },
  '1939-12': {
    lat: 50.3, lon: 6.5,
    ort: 'Eifel / Westwall (Einheitsstandort)',
    einheit: 'N.A. 20 / 20. Inf.Div.(mot.)',
    status: 'unbekannt',
    quelle: 'keine',
    popup_hinweis: 'KEIN individueller Nachweis.'
  },
  '1940-01': {
    lat: 50.3, lon: 6.5,
    ort: 'Eifel (Einheitsstandort)',
    einheit: 'N.A. 20 / 20. Inf.Div.(mot.)',
    status: 'unbekannt',
    quelle: 'keine',
    popup_hinweis: 'KEIN individueller Nachweis.'
  },
  '1940-02': {
    lat: 50.3, lon: 6.5,
    ort: 'Eifel (Einheitsstandort)',
    einheit: 'N.A. 20 / 20. Inf.Div.(mot.)',
    status: 'unbekannt',
    quelle: 'keine',
    popup_hinweis: 'KEIN individueller Nachweis.'
  },
  '1940-03': {
    lat: 50.3, lon: 6.5,
    ort: 'Eifel (Einheitsstandort)',
    einheit: 'N.A. 20 / 20. Inf.Div.(mot.)',
    status: 'unbekannt',
    quelle: 'keine',
    popup_hinweis: 'KEIN individueller Nachweis.'
  },
  '1940-04': {
    lat: 50.3, lon: 6.5,
    ort: 'Eifel (Einheitsstandort)',
    einheit: 'N.A. 20 / 20. Inf.Div.(mot.)',
    status: 'unbekannt',
    quelle: 'keine',
    popup_hinweis: 'KEIN individueller Nachweis.'
  },
  '1940-05': {
    lat: 50.85, lon: 4.35,
    ort: 'Belgien — Westfeldzug / Dyle-Stellung (Einheitsstandort)',
    einheit: 'N.A. 20 / 20. Inf.Div.(mot.)',
    status: 'unbekannt',
    quelle: 'keine',
    popup_hinweis: 'KEIN individueller Nachweis. Einheit laut Tessin in Belgien (Westfeldzug).'
  },
  '1940-06': {
    lat: 51.03, lon: 2.37,
    ort: 'Flandern / Dünkirchen (Einheitsstandort)',
    einheit: 'N.A. 20 / 20. Inf.Div.(mot.)',
    status: 'unbekannt',
    quelle: 'keine',
    popup_hinweis: 'KEIN individueller Nachweis. Einheit laut Tessin bei Dünkirchen.'
  },
  '1940-07': {
    lat: 47.5, lon: 1.5,
    ort: 'Frankreich — Besatzung (Einheitsstandort)',
    einheit: 'N.A. 20 / 20. Inf.Div.(mot.)',
    status: 'unbekannt',
    quelle: 'keine',
    popup_hinweis: 'KEIN individueller Nachweis. Einheit laut Tessin als Besatzungstruppe in Frankreich.'
  },
  '1940-08': { lat: 47.5, lon: 1.5, ort: 'Frankreich — Besatzung (Einheitsstandort)', einheit: 'N.A. 20 / 20. Inf.Div.(mot.)', status: 'unbekannt', quelle: 'keine', popup_hinweis: 'KEIN individueller Nachweis.' },
  '1940-09': { lat: 47.5, lon: 1.5, ort: 'Frankreich — Besatzung (Einheitsstandort)', einheit: 'N.A. 20 / 20. Inf.Div.(mot.)', status: 'unbekannt', quelle: 'keine', popup_hinweis: 'KEIN individueller Nachweis.' },
  '1940-10': { lat: 47.5, lon: 1.5, ort: 'Frankreich — Besatzung (Einheitsstandort)', einheit: 'N.A. 20 / 20. Inf.Div.(mot.)', status: 'unbekannt', quelle: 'keine', popup_hinweis: 'KEIN individueller Nachweis.' },
  '1940-11': { lat: 47.5, lon: 1.5, ort: 'Frankreich — Besatzung (Einheitsstandort)', einheit: 'N.A. 20 / 20. Inf.Div.(mot.)', status: 'unbekannt', quelle: 'keine', popup_hinweis: 'KEIN individueller Nachweis.' },
  '1940-12': { lat: 47.5, lon: 1.5, ort: 'Frankreich — Besatzung (Einheitsstandort)', einheit: 'N.A. 20 / 20. Inf.Div.(mot.)', status: 'unbekannt', quelle: 'keine', popup_hinweis: 'KEIN individueller Nachweis.' },
  '1941-01': { lat: 47.5, lon: 1.5, ort: 'Frankreich — Besatzung (Einheitsstandort)', einheit: 'N.A. 20 / 20. Inf.Div.(mot.)', status: 'unbekannt', quelle: 'keine', popup_hinweis: 'KEIN individueller Nachweis.' },
  '1941-02': { lat: 47.5, lon: 1.5, ort: 'Frankreich — Besatzung (Einheitsstandort)', einheit: 'N.A. 20 / 20. Inf.Div.(mot.)', status: 'unbekannt', quelle: 'keine', popup_hinweis: 'KEIN individueller Nachweis.' },
  '1941-03': { lat: 47.5, lon: 1.5, ort: 'Frankreich — Besatzung (Einheitsstandort)', einheit: 'N.A. 20 / 20. Inf.Div.(mot.)', status: 'unbekannt', quelle: 'keine', popup_hinweis: 'KEIN individueller Nachweis.' },
  '1941-04': { lat: 47.5, lon: 1.5, ort: 'Frankreich — Besatzung (Einheitsstandort)', einheit: 'N.A. 20 / 20. Inf.Div.(mot.)', status: 'unbekannt', quelle: 'keine', popup_hinweis: 'KEIN individueller Nachweis.' },
  '1941-05': {
    lat: 51.5, lon: 10.0,
    ort: 'Heimat — Verlegung Richtung Osten (Einheitsstandort)',
    einheit: 'N.A. 20 / 20. Inf.Div.(mot.)',
    status: 'unbekannt',
    quelle: 'keine',
    popup_hinweis: 'KEIN individueller Nachweis. Einheit laut Tessin: Rückverlegung aus Frankreich, Aufmarsch Ostpreußen.'
  },

  // ── Juni 1941: Barbarossa ─────────────────────────────────
  // Kein individueller Nachweis, aber N.A. 20 ist Divisionstruppe
  // der 20. Inf.Div.(mot.) die nachweislich bei Barbarossa dabei ist.
  // Tessin: Jun/Aug 1941 XXXIX. AK, 3. Pz.Gruppe, Hgr. Mitte → Białystok/Minsk

  '1941-06': {
    lat: 53.9, lon: 27.6,
    ort: 'Białystok / Minsk — Barbarossa-Beginn (Einheitsstandort)',
    einheit: 'N.A. 20 / 20. Inf.Div.(mot.)',
    status: 'einheit',
    quelle: 'tessin',
    popup_hinweis: 'Kein individueller Nachweis für 1941. Einheit laut Tessin Bd. 4: XXXIX. AK, 3. Pz.Gruppe, Hgr. Mitte. Operationen bei Białystok und Minsk.'
  },
  '1941-07': {
    lat: 53.9, lon: 27.6,
    ort: 'Minsk — Verlegung Nordabschnitt (Einheitsstandort)',
    einheit: 'N.A. 20 / 20. Inf.Div.(mot.)',
    status: 'einheit',
    quelle: 'tessin',
    popup_hinweis: 'Kein individueller Nachweis. Einheit laut Tessin: Verlegung nach Hgr. Nord.'
  },
  '1941-08': {
    lat: 59.6, lon: 33.5,
    ort: 'Ladogasee / Tichwin — Vormarsch auf Leningrad (Einheitsstandort)',
    einheit: 'N.A. 20 / 20. Inf.Div.(mot.)',
    status: 'einheit',
    quelle: 'tessin',
    popup_hinweis: 'Kein individueller Nachweis. Einheit laut Tessin: XXXIX. AK, 16. Armee, Hgr. Nord. Kämpfe südlich Ladogasee. Verlegung per Bahn aus Weißrussland.'
  },
  '1941-09': {
    lat: 59.6, lon: 33.5,
    ort: 'Ladogasee / Tichwin (Einheitsstandort)',
    einheit: 'N.A. 20 / 20. Inf.Div.(mot.)',
    status: 'einheit',
    quelle: 'tessin',
    popup_hinweis: 'Kein individueller Nachweis. Einheit laut Tessin: 16. Armee, Hgr. Nord.'
  },
  '1941-10': {
    lat: 59.1, lon: 31.7,
    ort: 'Wolchow-Front / Tschudowo (Einheitsstandort)',
    einheit: 'N.A. 20 / 20. Inf.Div.(mot.)',
    status: 'einheit',
    quelle: 'tessin',
    popup_hinweis: 'Kein individueller Nachweis. Einheit laut Tessin: I. AK, 18. Armee, Hgr. Nord. Beginn Stellungskrieg am Wolchow.'
  },
  '1941-11': { lat: 59.1, lon: 31.7, ort: 'Wolchow-Front / Tschudowo (Einheitsstandort)', einheit: 'N.A. 20 / 20. Inf.Div.(mot.)', status: 'einheit', quelle: 'tessin', popup_hinweis: 'Kein individueller Nachweis. Einheit: Wolchow-Front.' },
  '1941-12': { lat: 59.1, lon: 31.7, ort: 'Wolchow-Front — Winter 1941 (Einheitsstandort)', einheit: 'N.A. 20 / 20. Inf.Div.(mot.)', status: 'einheit', quelle: 'tessin', popup_hinweis: 'Kein individueller Nachweis. Einheit: Wolchow-Front.' },

  // ── 1942: Bundesarchiv belegt N.A. 20 UND Genesenden-Kompanie ──
  // "1. Kp. N.A. 20 gemeldet: 1942" → noch an der Front
  // "Stamm-Kp., Genesenden-Kp., 1. Genesenden-Kp. N.E.A. 20: 1942"
  // → Heimat Hamburg. Mehrfache Genesenden-Einheiten = längere Rekonvaleszenz.
  // Wann genau der Wechsel: unbekannt. Frühjahr 1942 vermutlich noch Front,
  // Sommer/Herbst 1942 Hamburg.

  '1942-01': {
    lat: 59.1, lon: 31.7,
    ort: 'Wolchow-Front (Einheitsstandort, noch N.A. 20 gemeldet)',
    einheit: 'N.A. 20 / 20. Inf.Div.(mot.)',
    status: 'einheit',
    quelle: 'bundesarchiv',
    popup_hinweis: 'Bundesarchiv belegt N.A. 20 für 1942 — also noch Fronteinsatz zu Jahresbeginn. Wann genau Wechsel zur Genesenden-Kompanie: unbekannt.'
  },
  '1942-02': { lat: 59.1, lon: 31.7, ort: 'Wolchow-Front (Einheitsstandort)', einheit: 'N.A. 20 / 20. Inf.Div.(mot.)', status: 'einheit', quelle: 'bundesarchiv', popup_hinweis: 'Bundesarchiv belegt N.A. 20 für 1942.' },
  '1942-03': { lat: 59.1, lon: 31.7, ort: 'Wolchow-Front (Einheitsstandort)', einheit: 'N.A. 20 / 20. Inf.Div.(mot.)', status: 'einheit', quelle: 'bundesarchiv', popup_hinweis: 'Bundesarchiv belegt N.A. 20 für 1942.' },
  '1942-04': { lat: 59.1, lon: 31.7, ort: 'Wolchow-Front (Einheitsstandort)', einheit: 'N.A. 20 / 20. Inf.Div.(mot.)', status: 'einheit', quelle: 'bundesarchiv', popup_hinweis: 'Bundesarchiv belegt N.A. 20 für 1942.' },

  // Ab ca. Sommer 1942: Genesenden-Kompanien Hamburg
  // Bundesarchiv: Stamm-Kp., Genesenden-Kp., 1. Genesenden-Kp. N.E.A. 20 — alle 1942
  // → Hamburg (WK X, Heimat)
  '1942-05': {
    lat: 53.6, lon: 10.0,
    ort: 'Hamburg — Genesenden-Kompanie N.E.A. 20 (vermutet)',
    einheit: 'Genesenden-Kp. N.E.A. 20',
    status: 'belegt',
    quelle: 'bundesarchiv',
    popup_hinweis: 'Bundesarchiv-Schreiben belegt mehrere Genesenden-Kompanien der N.E.A. 20 für 1942 in Hamburg. Genaues Datum des Beginns unbekannt — hier ab Mai 1942 angenommen. Möglicherweise frühere oder spätere Verwundung/Erkrankung.'
  },
  '1942-06': { lat: 53.6, lon: 10.0, ort: 'Hamburg — Genesenden-Kompanie N.E.A. 20', einheit: 'Genesenden-Kp. N.E.A. 20', status: 'belegt', quelle: 'bundesarchiv', popup_hinweis: 'Bundesarchiv belegt Genesenden-Kompanie Hamburg 1942.' },
  '1942-07': { lat: 53.6, lon: 10.0, ort: 'Hamburg — Genesenden-Kompanie N.E.A. 20', einheit: 'Genesenden-Kp. N.E.A. 20', status: 'belegt', quelle: 'bundesarchiv', popup_hinweis: 'Bundesarchiv belegt Genesenden-Kompanie Hamburg 1942.' },
  '1942-08': { lat: 53.6, lon: 10.0, ort: 'Hamburg — Genesenden-Kompanie N.E.A. 20', einheit: 'Genesenden-Kp. / 1. Genesenden-Kp. N.E.A. 20', status: 'belegt', quelle: 'bundesarchiv', popup_hinweis: 'Bundesarchiv belegt Genesenden-Kompanie Hamburg 1942.' },
  '1942-09': { lat: 53.6, lon: 10.0, ort: 'Hamburg — 1. Genesenden-Kompanie N.E.A. 20', einheit: '1. Genesenden-Kp. N.E.A. 20', status: 'belegt', quelle: 'bundesarchiv', popup_hinweis: 'Bundesarchiv belegt Genesenden-Kompanie Hamburg 1942. Mehrfache Eintragungen deuten auf längere Rekonvaleszenz hin.' },
  '1942-10': { lat: 53.6, lon: 10.0, ort: 'Hamburg — 1. Genesenden-Kompanie N.E.A. 20', einheit: '1. Genesenden-Kp. N.E.A. 20', status: 'belegt', quelle: 'bundesarchiv', popup_hinweis: 'Bundesarchiv belegt 1942.' },
  '1942-11': { lat: 53.6, lon: 10.0, ort: 'Hamburg — 1. Genesenden-Kompanie N.E.A. 20', einheit: '1. Genesenden-Kp. N.E.A. 20', status: 'belegt', quelle: 'bundesarchiv', popup_hinweis: 'Bundesarchiv belegt 1942.' },
  '1942-12': { lat: 53.6, lon: 10.0, ort: 'Hamburg — Rückkehr zur Einheit (vermutet)', einheit: 'N.E.A. 20 / Verlegung zur Front', status: 'einheit', quelle: 'tessin', popup_hinweis: 'Übergang zurück zur Fronteinheit. Tessin: Division bei Welish ab Dez. 1942.' },

  // ── 1943: Welish → Orel → VERWUNDUNG → LAZARETT ──────────
  // Bundesarchiv: "11. Kp. I.R. 90 gemeldet: 1943"
  // + "1. Marsch-Kp. G.E.B. 76 gemeldet: 1943"
  // + "Marsch-Kp. G.E.B. (mot.) 90 gemeldet: 1943"
  // Tessin: Welish (Jan-Mai), Orel (Jun-Jul), dann Rückzug
  // WASt-Karte I: Verwundung 28.08.1943 bei Gorki (BELEGT, sehr präzise)

  '1943-01': {
    lat: 55.6, lon: 31.2,
    ort: 'Welish — Hgr. Mitte (Einheitsstandort, I.R. 90)',
    einheit: 'I.R. 90 / 20. Inf.Div.(mot.)',
    status: 'einheit',
    quelle: 'bundesarchiv',
    popup_hinweis: 'Bundesarchiv belegt 11. Kp. I.R. 90 für 1943. Tessin: Division bei Welish, LIX. AK, 3. Pz.Armee, Hgr. Mitte.'
  },
  '1943-02': { lat: 55.6, lon: 31.2, ort: 'Welish (Einheitsstandort)', einheit: 'I.R. 90 / 20. Inf.Div.(mot.)', status: 'einheit', quelle: 'bundesarchiv', popup_hinweis: 'Bundesarchiv belegt I.R. 90 für 1943. Tessin: Welish.' },
  '1943-03': { lat: 55.6, lon: 31.2, ort: 'Welish (Einheitsstandort)', einheit: 'I.R. 90 / 20. Inf.Div.(mot.)', status: 'einheit', quelle: 'bundesarchiv', popup_hinweis: 'Tessin: Welish.' },
  '1943-04': { lat: 55.6, lon: 31.2, ort: 'Welish (Einheitsstandort)', einheit: 'I.R. 90 / 20. Inf.Div.(mot.)', status: 'einheit', quelle: 'bundesarchiv', popup_hinweis: 'Tessin: Welish.' },
  '1943-05': { lat: 55.6, lon: 31.2, ort: 'Welish (Einheitsstandort)', einheit: 'I.R. 90 / 20. Pz.Gren.Div.', status: 'einheit', quelle: 'bundesarchiv', popup_hinweis: 'Tessin: Welish. Division wird 23.06.1943 in 20. Pz.Gren.Div. umbenannt.' },
  '1943-06': {
    lat: 52.97, lon: 36.07,
    ort: 'Orel — Nordflügel Kursker Bogen (Einheitsstandort)',
    einheit: 'Pz.Gren.Rgt. 90 / 20. Pz.Gren.Div.',
    status: 'einheit',
    quelle: 'tessin',
    popup_hinweis: 'Tessin: LIII. AK, 2. Pz.Armee, Hgr. Mitte. Division OKH-Reserve, dann nördlich Kursk eingesetzt.'
  },
  '1943-07': {
    lat: 52.97, lon: 36.07,
    ort: 'Orel / Brjansk — Rückzugskämpfe nach Zitadelle (Einheitsstandort)',
    einheit: 'Pz.Gren.Rgt. 90 / 20. Pz.Gren.Div.',
    status: 'einheit',
    quelle: 'tessin',
    popup_hinweis: 'Tessin: XII. AK, 9. Armee, Hgr. Mitte. Schwere Abwehrkämpfe.'
  },

  // VERWUNDUNG: WASt-Karte I, präzisester Einzelbeleg
  '1943-08': {
    lat: 54.02, lon: 27.1,
    ort: 'Gorki, ca. 35 km südöstlich Ilija, Oblast Minsk',
    einheit: 'Pz.Gren.Rgt. 90 / 20. Pz.Gren.Div.',
    status: 'verwundet',
    quelle: 'wast_I',
    popup_hinweis: 'WASt-Karte I (Meldung I, eingeg. 20.04.1944): "Gorki etwa 35 km südostw. Illüja — leicht verw.: A.G. re. Ohr — abgeg.: H.V.Pl. 20 Pz.Gren.Div." Verwundungsdatum: 28.08.1943. Dies ist der präziseste geographische Einzelnachweis der gesamten Akte.'
  },

  // LAZARETTROUTE: WASt-Karte I, Meldungen 1–9 und Meldung II
  '1943-09': {
    lat: 51.4, lon: 21.15,
    ort: 'Radom — Kriegslazarett 3/605',
    einheit: '— (Lazarett)',
    status: 'lazarett',
    quelle: 'wast_I',
    popup_hinweis: 'WASt-Karte I, Meldung 2 (eingeg. 27.03.1944): "Rela. Radom, Lkb. 23787". Relazarettierung nach Radom ab 01.09.1943.'
  },
  '1943-10': {
    lat: 49.75, lon: 6.64,
    ort: 'Trier — Bürgerhospital / Reserve-Lazarett I',
    einheit: '— (Lazarett)',
    status: 'lazarett',
    quelle: 'wast_I',
    popup_hinweis: 'WASt-Karte I, Meldung 6 (eingeg. 27.03.1944): "Rela. Trier, Bürgerhospital, Lkb. 377". Mehrfache Relazarettierungen in Trier, Okt.–Nov. 1943.'
  },
  '1943-11': {
    lat: 50.81, lon: 8.77,
    ort: 'Marburg/Lahn — Reserve-Lazarett III, Ohrenklinik',
    einheit: '— (Lazarett)',
    status: 'lazarett',
    quelle: 'wast_I',
    popup_hinweis: 'WASt-Karte I, Meldung II (eingeg. 24.10.1944): "Res. Laz. III Marburg/Lahn, Ohrenklinik, Lkb. 364". Aufnahme 21.11.1943. Behandlung Granatsplitterverletzung rechtes Ohr.'
  },
  '1943-12': {
    lat: 50.81, lon: 8.77,
    ort: 'Marburg/Lahn — Reserve-Lazarett III, Ohrenklinik',
    einheit: '— (Lazarett)',
    status: 'lazarett',
    quelle: 'wast_I',
    popup_hinweis: 'WASt-Karte I: Res. Laz. III Marburg.'
  },
  '1944-01': {
    lat: 50.81, lon: 8.77,
    ort: 'Marburg/Lahn — Reserve-Lazarett III, Ohrenklinik',
    einheit: '— (Lazarett)',
    status: 'lazarett',
    quelle: 'wast_I',
    popup_hinweis: 'WASt-Karte I: Res. Laz. III Marburg.'
  },
  '1944-02': {
    lat: 50.81, lon: 8.77,
    ort: 'Marburg/Lahn — Reserve-Lazarett III, Ohrenklinik',
    einheit: '— (Lazarett)',
    status: 'lazarett',
    quelle: 'wast_I',
    popup_hinweis: 'WASt-Karte I: Res. Laz. III Marburg.'
  },

  // ENTLASSUNG: WASt-Karte I, Meldung II
  '1944-03': {
    lat: 53.57, lon: 10.13,
    ort: 'Hamburg-Wandsbek — Grenadier-Ersatz-Bataillon 90',
    einheit: 'Gren.Ers.Btl. 90',
    status: 'belegt',
    quelle: 'wast_I',
    popup_hinweis: 'WASt-Karte I, Meldung II: "Abg. a. 15.3.44, Abg. Gren.Ers.Btl. 90, Hamburg-Wandsbek." Entlassung aus Res.Laz. III Marburg am 15.03.1944. Bundesarchiv-Schreiben bestätigt G.E.B. 90 Hbg.-Wandsbek als Ersatztruppenstandort.'
  },

  // ── 1944: Rückkehr zur Front ──────────────────────────────
  // Kein weiterer WASt-Einzelbeleg nach März 1944.
  // Tessin: Division bei Kamenez-Podolsk (Apr), Brody (Jun-Jul),
  // Baranow/Weichsel (Aug-Nov), Kielce (Dez)

  '1944-04': {
    lat: 48.68, lon: 26.58,
    ort: 'Kamenez-Podolsk — Hube-Kessel / Ausbruch (Einheitsstandort)',
    einheit: 'Pz.Gren.Rgt. 90 / 20. Pz.Gren.Div.',
    status: 'einheit',
    quelle: 'tessin',
    popup_hinweis: 'Kein individueller Nachweis nach März 1944. Tessin: XXIV. Pz.AK, 1. Pz.Armee, Hgr. Süd. Ausbruch aus dem Hube-Kessel 28.03.–17.04.1944. Koppermann vermutlich nach Hamburg-Wandsbek zur Einheit zurückgekehrt.'
  },
  '1944-05': {
    lat: 49.84, lon: 24.03,
    ort: 'Brody / Westukraine — Auffrischung (Einheitsstandort)',
    einheit: 'Pz.Gren.Rgt. 90 / 20. Pz.Gren.Div.',
    status: 'einheit',
    quelle: 'tessin',
    popup_hinweis: 'Tessin: z.Vfg. 1. Pz.Armee, Hgr. Nordukraine. Auffrischung und Umgliederung.'
  },
  '1944-06': {
    lat: 49.84, lon: 24.03,
    ort: 'Brody / Lemberg — Einschließung und Ausbruch (Einheitsstandort)',
    einheit: 'Pz.Gren.Rgt. 90 / 20. Pz.Gren.Div.',
    status: 'einheit',
    quelle: 'tessin',
    popup_hinweis: 'Tessin: III. AK, 4. Pz.Armee, Hgr. Nordukraine. Gegenangriff südlich Lemberg, Einschließung bei Kamionka Strumilowa, Ausbruch nach 5 Tagen.'
  },
  '1944-07': {
    lat: 49.84, lon: 24.03,
    ort: 'Lemberg / Rückzug (Einheitsstandort)',
    einheit: 'Pz.Gren.Rgt. 90 / 20. Pz.Gren.Div.',
    status: 'einheit',
    quelle: 'tessin',
    popup_hinweis: 'Tessin: Abwehrkämpfe Zolkiew – Stary Sambor, südwestlich Lemberg.'
  },
  '1944-08': {
    lat: 50.5, lon: 21.52,
    ort: 'Baranow / Weichsel — Stellungskämpfe (Einheitsstandort)',
    einheit: 'Pz.Gren.Rgt. 90 / 20. Pz.Gren.Div.',
    status: 'einheit',
    quelle: 'tessin',
    popup_hinweis: 'Tessin: III. AK, 4. Pz.Armee, Hgr. Nordukraine/A. Sowjetischer Brückenkopf Baranow-Sandomierski — Ausgangspunkt der Weichsel-Oder-Offensive.'
  },
  '1944-09': { lat: 50.5, lon: 21.52, ort: 'Baranow / Weichsel — Stellungskämpfe (Einheitsstandort)', einheit: 'Pz.Gren.Rgt. 90 / 20. Pz.Gren.Div.', status: 'einheit', quelle: 'tessin', popup_hinweis: 'Tessin: XXXXVIII. Pz.AK, 4. Pz.Armee.' },
  '1944-10': { lat: 50.5, lon: 21.52, ort: 'Baranow / Weichsel — Stellungskämpfe (Einheitsstandort)', einheit: 'Pz.Gren.Rgt. 90 / 20. Pz.Gren.Div.', status: 'einheit', quelle: 'tessin', popup_hinweis: 'Tessin: XXXXVII. Pz.AK / Hgr. A.' },
  '1944-11': { lat: 50.5, lon: 21.52, ort: 'Baranow / Weichsel — Stellungskämpfe (Einheitsstandort)', einheit: 'Pz.Gren.Rgt. 90 / 20. Pz.Gren.Div.', status: 'einheit', quelle: 'tessin', popup_hinweis: 'Tessin: Hgr. A.' },
  '1944-12': {
    lat: 50.87, lon: 20.63,
    ort: 'Kielce / Weichselbogen — Auffrischung (Einheitsstandort)',
    einheit: 'Pz.Gren.Rgt. 90 / 20. Pz.Gren.Div.',
    status: 'einheit',
    quelle: 'tessin',
    popup_hinweis: 'Tessin: z.Vfg. Hgr. A. Auffrischung bei Kielce. Stanford-Grenzdaten enden Nov. 1944 — Hintergrundkarte eingefroren.'
  },

  // VERMISST: WASt-Karte II, Eintrag 25.07.1986
  '1945-01': {
    lat: 50.87, lon: 20.63,
    ort: 'Weichselbogen, Raum Kielce — VERMISST 13.01.1945',
    einheit: 'Pz.Gren.Rgt. 90 / 20. Pz.Gren.Div.',
    status: 'vermisst',
    quelle: 'wast_II',
    popup_hinweis: 'WASt-Karte II (Eintrag 25.07.1986): "Ausw.: 13.1.45 vermisst." Lt. Vorl.-Meldg. Bd. A 620, eingesandt 19.07.1984 vom B.R./Z.N.S. Die sowjetische Weichsel-Oder-Offensive beginnt am 12.01.1945. Familienüberlieferung: Schussverletzung, Transport auf Lafette, Wundbrand, Beinverlust.'
  },
};

// ═══════════════════════════════════════════════════════════
// Visuelle Kodierung nach status (für Claude Code):
//
// 'belegt'    → solider Punkt, grün (#1D9E75), Rand weiß
// 'einheit'   → gestrichelter Kreis, grün, halbtransparent
// 'unbekannt' → Fragezeichen-Icon, grau (#888), klein
// 'lazarett'  → Kreuz-Symbol, lila (#7D3C98)
// 'verwundet' → Stern + Kreuz kombiniert, orange (#E8A838), größer
// 'vermisst'  → Fragezeichen, dunkelgrau (#444), pulsierend
//
// Im Popup immer popup_hinweis anzeigen und quelle nennen.
// Bei status 'unbekannt': Hinweis fett/rot: "Kein individueller Nachweis"
// ═══════════════════════════════════════════════════════════
