// Shared UI translation dictionary + a small t() lookup helper.
//
// Coverage is deliberately scoped to the highest-traffic surfaces
// (header, landing page, chat composer, results page, advisor
// button, nav menu, accounts pages) rather than every string in the
// app — deep modal copy and rare error messages still fall back to
// English via the lookup's fallback behavior. isiZulu and Igbo
// entries are a best-effort first draft, not reviewed by a native or
// professional speaker; get these checked before real client use,
// same caveat as the chat's own language support.
export const LANGUAGES = [
  { code: "en", label: "English", flag: "🇬🇧" },
  { code: "zu", label: "isiZulu", flag: "🇿🇦" },
  { code: "sw", label: "Swahili", flag: "🇰🇪" },
  { code: "ig", label: "Igbo", flag: "🇳🇬" },
  { code: "pt", label: "Portuguese", flag: "🇵🇹" },
];

export const UI_STRINGS = {
  en: {
    header: { product: "Horizon AI", chooseLanguage: "Language" },
    nav: {
      home: "Home",
      profiles: "My Profiles",
      accounts: "My Accounts",
      settings: "Profile settings",
      logout: "Log out",
      login: "Log in",
    },
    advisor: {
      trigger: "Talk to an Advisor",
      title: "Talk to an advisor",
      subtitle: "Choose how you'd like to connect.",
      call: "Call us",
      callback: "Request a callback",
      callbackSub: "We'll call you back shortly",
      close: "Close",
      requested: "Request received — an advisor will call you back shortly.",
    },
    landing: {
      headline: "Hi! I'm Horizon AI, your Standard Bank Financial Guide.",
      slogan: "See what tomorrow could look like.",
      subtext: "Tell me what you're hoping to achieve, and I'll help you understand your options, in your language.",
      placeholder: "How can I help you today?",
      pills: { retirement: "Retirement", investments: "Investments", protection: "Protection", savings: "Savings" },
    },
    chat: {
      placeholderIntake: "Type your answer…",
      placeholderResults: "Ask a question, e.g. what if I invest more?",
      listening: "Listening…",
      send: "Send",
      hideChat: "Hide chat",
      askAboutResults: "Ask about your results",
    },
    results: {
      title: "Your risk matrix",
      goals: "Goals",
      matchedProducts: "Matched products",
      scenarioProducts: "Products under this scenario",
      yourAccounts: "Your accounts",
      preview: "Preview",
      actualResults: "My actual results",
      showMore: "Show more",
      showLess: "Show less",
      noProducts: "No products currently match — capital protection only, or nothing fits these amounts yet.",
      disclaimer: "Projections use illustrative return assumptions and are not guaranteed — actual investment performance will vary.",
      investNow: "Invest Now",
      recommendedSplit: "Recommended split across portfolios",
      overallBand: "Overall band",
      tolerance: "Tolerance",
      capacity: "Capacity",
      horizon: "Horizon",
      taxBracket: "Tax bracket",
      note: 'Governed by the lowest of tolerance (your comfort with risk), capacity (what you can financially afford to risk), and horizon (how long until you need this money) — the dot on the ladder shows which one is constraining. Ask the chat "what if I invest more" to see how the numbers below change.',
      bandLabels: {
        1: "Very Cautious",
        2: "Cautious",
        3: "Balanced",
        4: "Growth-Focused",
        5: "Aggressive Growth",
      },
      bandExplanations: {
        1: "We've matched you with the most capital-stable options available. Protecting what you already have matters more right now than chasing higher returns.",
        2: "A gentle mix that limits how much you could lose, while still allowing some room to grow.",
        3: "A balanced mix of growth and stability — comfortable with some ups and downs along the way in exchange for better long-term returns.",
        4: "Tilted toward growth. You're comfortable with real short-term swings in your investment's value, in exchange for stronger long-term potential.",
        5: "Full growth focus. You're comfortable with significant ups and downs along the way, in pursuit of the highest long-term potential.",
      },
    },
    accounts: {
      title: "My accounts",
      back: "Back",
      linkedAccounts: "Your linked accounts",
      investmentAccounts: "Your investment accounts",
      noInvestmentAccounts: "No investment accounts yet — complete a risk profile and use Invest Now to open your first one.",
      pending: "Pending review",
    },
    profile: {
      title: "My profile",
      edit: "Edit profile",
      save: "Save",
      cancel: "Cancel",
      logout: "Log out",
    },
    common: {
      back: "Back",
      close: "Close",
      loading: "Loading…",
    },
  },
  pt: {
    header: { product: "Horizon AI", chooseLanguage: "Idioma" },
    nav: {
      home: "Início",
      profiles: "Meus Perfis",
      accounts: "Minhas Contas",
      settings: "Configurações do perfil",
      logout: "Sair",
      login: "Entrar",
    },
    advisor: {
      trigger: "Falar com um Consultor",
      title: "Falar com um consultor",
      subtitle: "Escolha como deseja se conectar.",
      call: "Ligue para nós",
      callback: "Solicitar retorno de chamada",
      callbackSub: "Ligaremos para você em breve",
      close: "Fechar",
      requested: "Pedido recebido — um consultor irá ligar para si em breve.",
    },
    landing: {
      headline: "Olá! Sou o Horizon AI, o seu Guia Financeiro do Standard Bank.",
      slogan: "Veja como pode ser o amanhã.",
      subtext: "Diga-me o que espera alcançar, e eu ajudo a entender as suas opções, no seu idioma.",
      placeholder: "Como posso ajudar hoje?",
      pills: { retirement: "Reforma", investments: "Investimentos", protection: "Proteção", savings: "Poupança" },
    },
    chat: {
      placeholderIntake: "Digite sua resposta…",
      placeholderResults: "Faça uma pergunta, ex.: e se eu investir mais?",
      listening: "Ouvindo…",
      send: "Enviar",
      hideChat: "Ocultar chat",
      askAboutResults: "Pergunte sobre os seus resultados",
    },
    results: {
      title: "A sua matriz de risco",
      goals: "Objetivos",
      matchedProducts: "Produtos correspondides",
      scenarioProducts: "Produtos neste cenário",
      yourAccounts: "As suas contas",
      preview: "Pré-visualização",
      actualResults: "Meus resultados reais",
      showMore: "Mostrar mais",
      showLess: "Mostrar menos",
      noProducts: "Nenhum produto corresponde atualmente.",
      disclaimer: "As projeções usam pressupostos de retorno ilustrativos e não são garantidas — o desempenho real do investimento irá variar.",
      investNow: "Investir Agora",
      recommendedSplit: "Divisão recomendada entre carteiras",
      overallBand: "Banda geral",
      tolerance: "Tolerância",
      capacity: "Capacidade",
      horizon: "Horizonte",
      taxBracket: "Faixa de imposto",
      note: 'Regido pelo menor entre tolerância (o seu conforto com o risco), capacidade (o que pode financeiramente arriscar) e horizonte (quanto tempo até precisar deste dinheiro) — o ponto na escada mostra qual está a limitar. Pergunte ao chat "e se eu investir mais" para ver como os números abaixo mudam.',
      bandLabels: {
        1: "Muito Cauteloso",
        2: "Cauteloso",
        3: "Equilibrado",
        4: "Focado em Crescimento",
        5: "Crescimento Agressivo",
      },
      bandExplanations: {
        1: "Combinámo-lo com as opções mais estáveis em capital disponíveis. Proteger o que já tem importa mais agora do que perseguir retornos mais altos.",
        2: "Uma combinação suave que limita quanto poderia perder, ao mesmo tempo que permite algum espaço para crescer.",
        3: "Uma combinação equilibrada de crescimento e estabilidade — confortável com algumas subidas e descidas pelo caminho em troca de melhores retornos a longo prazo.",
        4: "Inclinado para o crescimento. Você está confortável com oscilações reais de curto prazo no valor do seu investimento, em troca de um potencial mais forte a longo prazo.",
        5: "Foco total no crescimento. Você está confortável com subidas e descidas significativas pelo caminho, em busca do maior potencial a longo prazo.",
      },
    },
    accounts: {
      title: "Minhas contas",
      back: "Voltar",
      linkedAccounts: "As suas contas vinculadas",
      investmentAccounts: "As suas contas de investimento",
      noInvestmentAccounts: "Ainda sem contas de investimento — complete um perfil de risco e use Investir Agora.",
      pending: "Em análise",
    },
    profile: {
      title: "Meu perfil",
      edit: "Editar perfil",
      save: "Guardar",
      cancel: "Cancelar",
      logout: "Sair",
    },
    common: { back: "Voltar", close: "Fechar", loading: "Carregando…" },
  },
  sw: {
    header: { product: "Horizon AI", chooseLanguage: "Lugha" },
    nav: {
      home: "Nyumbani",
      profiles: "Wasifu Wangu",
      accounts: "Akaunti Zangu",
      settings: "Mipangilio ya wasifu",
      logout: "Toka",
      login: "Ingia",
    },
    advisor: {
      trigger: "Zungumza na Mshauri",
      title: "Zungumza na mshauri",
      subtitle: "Chagua jinsi ungependa kuungana.",
      call: "Tupigie simu",
      callback: "Omba kupigiwa simu",
      callbackSub: "Tutakupigia simu hivi karibuni",
      close: "Funga",
      requested: "Ombi limepokelewa — mshauri atakupigia simu hivi karibuni.",
    },
    landing: {
      headline: "Habari! Mimi ni Horizon AI, Mwongozo wako wa Kifedha wa Standard Bank.",
      slogan: "Ona jinsi kesho inavyoweza kuwa.",
      subtext: "Niambie unachotaka kufikia, nami nitakusaidia kuelewa chaguo zako, kwa lugha yako.",
      placeholder: "Ninawezaje kukusaidia leo?",
      pills: { retirement: "Ustaafu", investments: "Uwekezaji", protection: "Ulinzi", savings: "Akiba" },
    },
    chat: {
      placeholderIntake: "Andika jibu lako…",
      placeholderResults: "Uliza swali, mfano: itakuwaje nikiwekeza zaidi?",
      listening: "Inasikiliza…",
      send: "Tuma",
      hideChat: "Ficha mazungumzo",
      askAboutResults: "Uliza kuhusu matokeo yako",
    },
    results: {
      title: "Wasifu wako wa hatari",
      goals: "Malengo",
      matchedProducts: "Bidhaa zinazolingana",
      scenarioProducts: "Bidhaa chini ya hali hii",
      yourAccounts: "Akaunti zako",
      preview: "Hakiki",
      actualResults: "Matokeo yangu halisi",
      showMore: "Onyesha zaidi",
      showLess: "Onyesha kidogo",
      noProducts: "Hakuna bidhaa zinazolingana kwa sasa.",
      disclaimer: "Makadirio hutumia mawazo ya mfano ya mapato na hayahakikishwi — utendaji halisi wa uwekezaji utatofautiana.",
      investNow: "Wekeza Sasa",
      recommendedSplit: "Mgawanyo unaopendekezwa kati ya portfolios",
      overallBand: "Kiwango cha jumla",
      tolerance: "Uvumilivu",
      capacity: "Uwezo",
      horizon: "Muda",
      taxBracket: "Kiwango cha kodi",
      note: 'Inaongozwa na kiwango cha chini kati ya uvumilivu (starehe yako na hatari), uwezo (unachoweza kumudu kifedha kuhatarisha), na muda (ni muda gani hadi uhitaji pesa hii) — nukta kwenye ngazi inaonyesha ni ipi inayozuia. Uliza mazungumzo "itakuwaje nikiwekeza zaidi" kuona jinsi namba zilizo chini zinavyobadilika.',
      bandLabels: {
        1: "Mwangalifu Sana",
        2: "Mwangalifu",
        3: "Uwiano",
        4: "Unaolenga Ukuaji",
        5: "Ukuaji wa Nguvu",
      },
      bandExplanations: {
        1: "Tumekulinganisha na chaguo zenye uthabiti mkubwa wa mtaji zinazopatikana. Kulinda ulicho nacho tayari ni muhimu zaidi sasa kuliko kufuatilia faida kubwa zaidi.",
        2: "Mchanganyiko wa upole unaozuia kiasi unachoweza kupoteza, huku bado ukiruhusu nafasi ya kukua.",
        3: "Mchanganyiko uliosawazishwa wa ukuaji na uthabiti — starehe na baadhi ya kupanda na kushuka njiani kwa kubadilishana na faida bora za muda mrefu.",
        4: "Umeelekea kwenye ukuaji. Uko starehe na mabadiliko halisi ya muda mfupi katika thamani ya uwekezaji wako, kwa kubadilishana na uwezo bora wa muda mrefu.",
        5: "Lengo kamili la ukuaji. Uko starehe na kupanda na kushuka kukubwa njiani, katika kutafuta uwezo mkubwa zaidi wa muda mrefu.",
      },
    },
    accounts: {
      title: "Akaunti zangu",
      back: "Rudi",
      linkedAccounts: "Akaunti zako zilizounganishwa",
      investmentAccounts: "Akaunti zako za uwekezaji",
      noInvestmentAccounts: "Bado hakuna akaunti za uwekezaji.",
      pending: "Inasubiri ukaguzi",
    },
    profile: {
      title: "Wasifu wangu",
      edit: "Hariri wasifu",
      save: "Hifadhi",
      cancel: "Ghairi",
      logout: "Toka",
    },
    common: { back: "Rudi", close: "Funga", loading: "Inapakia…" },
  },
  zu: {
    header: { product: "Horizon AI", chooseLanguage: "Ulimi" },
    nav: {
      home: "Ekhaya",
      profiles: "Amaphrofayela Ami",
      accounts: "Ama-akhawunti Ami",
      settings: "Izilungiselelo zephrofayela",
      logout: "Phuma",
      login: "Ngena",
    },
    advisor: {
      trigger: "Khuluma Nomeluleki",
      title: "Khuluma nomeluleki",
      subtitle: "Khetha indlela ofuna ukuxhumana ngayo.",
      call: "Sishayele",
      callback: "Cela ukushayelwa",
      callbackSub: "Sizokushayela maduze",
      close: "Vala",
      requested: "Isicelo sitholiwe — umeluleki uzokushayela maduze.",
    },
    landing: {
      headline: "Sawubona! NginguHorizon AI, umhlahlandlela wakho wezezimali we-Standard Bank.",
      slogan: "Bona ukuthi ikusasa lingaba kanjani.",
      subtext: "Ngitshele ofuna ukukufeza, futhi ngizokusiza uqonde izinketho zakho, ngolimi lwakho.",
      placeholder: "Ngingakusiza kanjani namuhla?",
      pills: { retirement: "Umhlalaphansi", investments: "Ukutshala imali", protection: "Ukuvikela", savings: "Ukonga" },
    },
    chat: {
      placeholderIntake: "Bhala impendulo yakho…",
      placeholderResults: "Buza umbuzo, isb. kuzoba njani uma ngitshala kakhulu?",
      listening: "Iyalalela…",
      send: "Thumela",
      hideChat: "Fihla ingxoxo",
      askAboutResults: "Buza mayelana nemiphumela yakho",
    },
    results: {
      title: "Imethriksi yakho yobungozi",
      goals: "Izinjongo",
      matchedProducts: "Imikhiqizo efanayo",
      scenarioProducts: "Imikhiqizo ngaphansi kwalesi simo",
      yourAccounts: "Ama-akhawunti akho",
      preview: "Ukubuka kuqala",
      actualResults: "Imiphumela yami yangempela",
      showMore: "Bonisa okwengeziwe",
      showLess: "Bonisa okuncane",
      noProducts: "Ayikho imikhiqizo efanayo okwamanje.",
      disclaimer: "Ukubikezela kusebenzisa izinto ezicatshangwayo hhayi eziqinisekisiwe.",
      investNow: "Tshala Manje",
      recommendedSplit: "Ukwahlukaniswa okuncomekayo kuma-portfolios",
      overallBand: "Ibhange elivamile",
      tolerance: "Ukubekezelela",
      capacity: "Amandla",
      horizon: "Isikhathi",
      taxBracket: "Izinga lentela",
      note: 'Kulawulwa ubuncane phakathi kokubekezelela (ukukhululeka kwakho ngobungozi), amandla (lokho ongakwazi ukubeka engozini ngokwezimali), kanye nesikhathi (isikhathi esingakanani ngaphambi kokuba udinge le mali) — ichaphaza kuleli bhalansi likhombisa yiliphi elivimbelayo. Buza ingxoxo "kuzoba njani uma ngitshala kakhulu" ukuze ubone ukuthi izinombolo ezingezansi zishintsha kanjani.',
      bandLabels: {
        1: "Oqaphile Kakhulu",
        2: "Oqaphile",
        3: "Olinganisiwe",
        4: "Ogxile Ekukhuleni",
        5: "Ukukhula Okunamandla",
      },
      bandExplanations: {
        1: "Sikuhlanganise nezinketho ezinokuzinza okukhulu kwemali okhona. Ukuvikela lokho osele unakho kubaluleke kakhulu manje kunokulandela inzuzo ephakeme.",
        2: "Inhlanganisela emnene evimbela ukuthi kungakanani ongase ulahlekelwe kukho, kuyilapho kusavumela isikhala sokukhula.",
        3: "Inhlanganisela elinganisiwe yokukhula nokuzinza — okhululekile ngokukhuphuka nokwehla okuthile endleleni ukuze uthole inzuzo engcono yesikhathi eside.",
        4: "Kugobele ekukhuleni. Ukhululekile ngokuguquguquka kwangempela kwesikhathi esifushane enanini lokutshalwa kwakho kwemali, ukuze uthole amandla angcono esikhathi eside.",
        5: "Ukugxila okugcwele ekukhuleni. Ukhululekile ngokukhuphuka nokwehla okukhulu endleleni, ufuna amandla aphezulu kakhulu esikhathi eside.",
      },
    },
    accounts: {
      title: "Ama-akhawunti ami",
      back: "Emuva",
      linkedAccounts: "Ama-akhawunti akho ahlotshaniswayo",
      investmentAccounts: "Ama-akhawunti akho okutshala imali",
      noInvestmentAccounts: "Awukabi na-akhawunti yokutshala imali.",
      pending: "Kusalindwe ukubuyekezwa",
    },
    profile: {
      title: "Iphrofayela yami",
      edit: "Hlela iphrofayela",
      save: "Londoloza",
      cancel: "Khansela",
      logout: "Phuma",
    },
    common: { back: "Emuva", close: "Vala", loading: "Iyalayisha…" },
  },
  ig: {
    header: { product: "Horizon AI", chooseLanguage: "Asụsụ" },
    nav: {
      home: "Ụlọ",
      profiles: "Profaịlụ M",
      accounts: "Akaụntụ M",
      settings: "Ntọala profaịlụ",
      logout: "Pụọ",
      login: "Banye",
    },
    advisor: {
      trigger: "Gwa Onye Ndụmọdụ Okwu",
      title: "Gwa onye ndụmọdụ okwu",
      subtitle: "Họrọ otu ị chọrọ iji jikọọ.",
      call: "Kpọọ anyị",
      callback: "Rịọ ka a kpọghachi gị",
      callbackSub: "Anyị ga-akpọghachi gị n'oge na-adịghị anya",
      close: "Mechie",
      requested: "Anatala arịrịọ — onye ndụmọdụ ga-akpọghachi gị n'oge na-adịghị anya.",
    },
    landing: {
      headline: "Ndewo! Abụ m Horizon AI, Onye Ndụmọdụ Ego gị nke Standard Bank.",
      slogan: "Hụ ka echi nwere ike ịdị.",
      subtext: "Gwa m ihe ị na-achọ imezu, m ga-enyere gị aka ịghọta nhọrọ gị, n'asụsụ gị.",
      placeholder: "Kedu ka m ga-esi nyere gị aka taa?",
      pills: { retirement: "Ezumike ọgụgụ", investments: "Itinye ego", protection: "Nchekwa", savings: "Ịchekwa ego" },
    },
    chat: {
      placeholderIntake: "Dee azịza gị…",
      placeholderResults: "Jụọ ajụjụ, dịka: gịnị ga-eme ma ọ bụrụ na m tinye ego karịa?",
      listening: "Na-ege ntị…",
      send: "Ziga",
      hideChat: "Zoo mkparịta ụka",
      askAboutResults: "Jụọ maka nsonaazụ gị",
    },
    results: {
      title: "Matriks ihe ize ndụ gị",
      goals: "Ebumnuche",
      matchedProducts: "Ngwaahịa dabara",
      scenarioProducts: "Ngwaahịa n'okpuru ọnọdụ a",
      yourAccounts: "Akaụntụ gị",
      preview: "Nlele mbụ",
      actualResults: "Nsonaazụ m n'ezie",
      showMore: "Gosi ọzọ",
      showLess: "Gosi ntakịrị",
      noProducts: "Enweghị ngwaahịa dabara ugbu a.",
      disclaimer: "Amụma na-eji echiche nnata atụmatụ, ọ bụghị nke akwadoro — ọrụ itinye ego n'ezie ga-adịgasị iche.",
      investNow: "Tinye Ego Ugbu a",
      recommendedSplit: "Nkewa akwadoro n'etiti portfolios",
      overallBand: "Ogo izugbe",
      tolerance: "Ndidi",
      capacity: "Ike",
      horizon: "Oge",
      taxBracket: "Ọkwa ụtụ isi",
      note: 'A na-achịkwa ya site n\'obere kacha nta n\'etiti ndidi (ka ahụ ị dị mma na ihe ize ndụ), ike (ihe ị nwere ike iji ego tinye n\'ihe ize ndụ), na oge (ogologo oge ị ga-achọ ego a) — ntụpọ dị na ubube ahụ na-egosi nke na-egbochi. Jụọ mkparịta ụka "gịnị ga-eme ma ọ bụrụ na m tinye ego karịa" iji hụ ka ọnụọgụ dị n\'okpuru si agbanwe.',
      bandLabels: {
        1: "Nlezịanya Nke Ukwu",
        2: "Nlezịanya",
        3: "Nguzoziga",
        4: "Elekwasị Uto",
        5: "Uto Ike Ike",
      },
      bandExplanations: {
        1: "Anyị ejikọtala gị na nhọrọ kacha nwee nchekwa ego dị. Ichekwa ihe ị nweburu na-aba uru karịa ịchụsọ ọghọ ndị ka elu ugbu a.",
        2: "Ngwakọta dị nwayọ na-egbochi ego ole ị nwere ike ịtụfu, ka ọ na-enyekwa ohere ịto.",
        3: "Ngwakọta ziga zi nke uto na nguzozi — na-anụ ahụ mma na mgbago na mgbada ụfọdụ n'ụzọ maka ọghọ ka mma n'ogologo oge.",
        4: "Gbadaruo n'uto. Ọ na-anụ ahụ mma na mgbanwe ezigbo nke oge dị nkenke n'ọnụ ahịa itinye ego gị, maka ike ka ike n'ogologo oge.",
        5: "Nlebara uto zuru oke. Ọ na-anụ ahụ mma na mgbago na mgbada dị ukwuu n'ụzọ, na-achọ ike kachasị elu n'ogologo oge.",
      },
    },
    accounts: {
      title: "Akaụntụ m",
      back: "Laghachi",
      linkedAccounts: "Akaụntụ gị ejikọtara",
      investmentAccounts: "Akaụntụ itinye ego gị",
      noInvestmentAccounts: "Enwebeghị akaụntụ itinye ego.",
      pending: "Na-eche nyocha",
    },
    profile: {
      title: "Profaịlụ m",
      edit: "Dezie profaịlụ",
      save: "Chekwaa",
      cancel: "Kagbuo",
      logout: "Pụọ",
    },
    common: { back: "Laghachi", close: "Mechie", loading: "Na-ebu…" },
  },
};

// Dotted-path lookup with English fallback at both the language and
// key level, so a partially-translated section (or a language not in
// UI_STRINGS at all) never renders blank — worst case it shows English.
export function t(language, path) {
  const dict = UI_STRINGS[language] || UI_STRINGS.en;
  const parts = path.split(".");
  let node = dict;
  for (const part of parts) {
    node = node?.[part];
  }
  if (node === undefined) {
    let fallback = UI_STRINGS.en;
    for (const part of parts) {
      fallback = fallback?.[part];
    }
    return fallback ?? path;
  }
  return node;
}

// Proactive account-notification copy — kept separate from UI_STRINGS
// since these are fill-in-the-blank templates ({product}/{portfolio})
// rather than plain strings. The backend only sends English copy plus
// the structured product/portfolio names (see NotificationOut) so
// this builds the actually-displayed text from those names against a
// translated template, the same fix used for the risk band labels —
// otherwise notifications would silently stay English regardless of
// the selected language.
export const NOTIFICATION_TEMPLATES = {
  en: {
    title: "Notifications",
    empty: "Nothing new right now.",
    checkin: {
      message: "It's been a little while since you opened {product} — still happy with how it's going?",
      ctaLabel: "Check in about this",
      ctaMessage: "It's been a while since I opened {product} — can we review whether it's still the right fit for me?",
    },
    income_increase: {
      message: "Your income looks like it's grown since you set up {product} — want to see if increasing your monthly contribution makes sense?",
      ctaLabel: "Explore increasing my contribution",
      ctaMessage: "My income has increased since I set up {product} — what would happen if I increased my monthly contribution?",
    },
    portfolio_update: {
      message: "There may be a lower-fee option available for {portfolio} within {product} — want to see how switching could look?",
      ctaLabel: "See if switching helps",
      ctaMessage: "Is there a lower-fee alternative to {portfolio} within {product} that I should consider?",
    },
  },
  pt: {
    title: "Notificações",
    empty: "Nada de novo por agora.",
    checkin: {
      message: "Já faz um tempo desde que abriu {product} — ainda está satisfeito com o andamento?",
      ctaLabel: "Fazer um ponto de situação",
      ctaMessage: "Já faz um tempo desde que abri {product} — podemos rever se ainda é a melhor opção para mim?",
    },
    income_increase: {
      message: "O seu rendimento parece ter aumentado desde que configurou {product} — quer ver se faz sentido aumentar a sua contribuição mensal?",
      ctaLabel: "Explorar aumentar a minha contribuição",
      ctaMessage: "O meu rendimento aumentou desde que configurei {product} — o que aconteceria se aumentasse a minha contribuição mensal?",
    },
    portfolio_update: {
      message: "Pode haver uma opção com taxa mais baixa disponível para {portfolio} dentro de {product} — quer ver como seria mudar?",
      ctaLabel: "Ver se mudar ajuda",
      ctaMessage: "Existe uma alternativa com taxa mais baixa a {portfolio} dentro de {product} que eu deva considerar?",
    },
  },
  sw: {
    title: "Arifa",
    empty: "Hakuna kipya kwa sasa.",
    checkin: {
      message: "Imepita muda tangu ufungue {product} — bado uko radhi na jinsi inavyoenda?",
      ctaLabel: "Angalia kuhusu hili",
      ctaMessage: "Imepita muda tangu nifungue {product} — tunaweza kupitia kama bado ni sahihi kwangu?",
    },
    income_increase: {
      message: "Kipato chako kinaonekana kimeongezeka tangu uanzishe {product} — unataka kuona kama kuongeza mchango wako wa kila mwezi kuna maana?",
      ctaLabel: "Chunguza kuongeza mchango wangu",
      ctaMessage: "Kipato changu kimeongezeka tangu nianzishe {product} — nini kingetokea nikiongeza mchango wangu wa kila mwezi?",
    },
    portfolio_update: {
      message: "Kunaweza kuwa na chaguo la ada ya chini kwa {portfolio} ndani ya {product} — unataka kuona jinsi kubadilisha kunavyoweza kuwa?",
      ctaLabel: "Angalia kama kubadilisha kutasaidia",
      ctaMessage: "Je, kuna mbadala wa ada ya chini kwa {portfolio} ndani ya {product} ambao ninapaswa kuzingatia?",
    },
  },
  zu: {
    title: "Izaziso",
    empty: "Akukho okusha okwamanje.",
    checkin: {
      message: "Sekuyisikhathi kusukela wavula i-{product} — usajabulile ngendlela ekuhamba ngayo?",
      ctaLabel: "Hlola ngalokhu",
      ctaMessage: "Sekuyisikhathi kusukela ngavula i-{product} — singahlola ukuthi isafanele yini kimi?",
    },
    income_increase: {
      message: "Imali engenayo ibonakala ikhulile kusukela wasungula i-{product} — ufuna ukubona ukuthi kunengqondo yini ukwandisa umnikelo wakho wanyanga zonke?",
      ctaLabel: "Hlola ukwandisa umnikelo wami",
      ctaMessage: "Imali engenayo yami ikhulile kusukela ngasungula i-{product} — kungenzekani uma ngandisa umnikelo wami wanyanga zonke?",
    },
    portfolio_update: {
      message: "Kungaba khona inketho enenkokhelo ephansi ye-{portfolio} ngaphakathi kwe-{product} — ufuna ukubona ukuthi ukushintsha kungaba njani?",
      ctaLabel: "Bona ukuthi ukushintsha kuyasiza",
      ctaMessage: "Ingabe kukhona enye inketho enenkokhelo ephansi ku-{portfolio} ngaphakathi kwe-{product} okufanele ngiyicabangele?",
    },
  },
  ig: {
    title: "Ọkwa",
    empty: "Enweghị ihe ọhụrụ ugbu a.",
    checkin: {
      message: "Ọ marula oge site mgbe i meghere {product} — ka ọ na-atọ gị ụtọ otu ọ na-aga?",
      ctaLabel: "Lelee gburugburu nke a",
      ctaMessage: "Ọ marula oge site mgbe m meghere {product} — anyị nwere ike ilele ma ọ ka dabara nma maka m?",
    },
    income_increase: {
      message: "Ego ọnụego gị yiri ka o toworo site mgbe i hiwere {product} — ị chọrọ ịhụ ma ọ ga-aba uru ịbawanye onyinye gị kwa ọnwa?",
      ctaLabel: "Nyochaa ịbawanye onyinye m",
      ctaMessage: "Ego ọnụego m abawanyela site mgbe m hiwere {product} — gịnị ga-eme ma ọ bụrụ na m bawanye onyinye m kwa ọnwa?",
    },
    portfolio_update: {
      message: "Enwere ike inwe nhọrọ ụgwọ ọrụ dị ala maka {portfolio} n'ime {product} — ị chọrọ ịhụ ka ịgbanwe nwere ike ịdị?",
      ctaLabel: "Hụ ma ịgbanwe ga-enyere aka",
      ctaMessage: "O nwere ihe ọzọ dị ala n'ụgwọ ọrụ maka {portfolio} n'ime {product} m kwesịrị ịtụle?",
    },
  },
};

export function formatNotification(language, notif) {
  const templates = NOTIFICATION_TEMPLATES[language] || NOTIFICATION_TEMPLATES.en;
  const tpl = templates[notif.type] || NOTIFICATION_TEMPLATES.en[notif.type];
  if (!tpl) {
    return { message: notif.message, ctaLabel: notif.cta_label, ctaMessage: notif.cta_message };
  }
  const fill = (s) =>
    s.replace("{product}", notif.product_name || "").replace("{portfolio}", notif.portfolio_name || "");
  return { message: fill(tpl.message), ctaLabel: tpl.ctaLabel, ctaMessage: fill(tpl.ctaMessage) };
}
