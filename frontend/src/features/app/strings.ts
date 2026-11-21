/**
 * Words for the app screens (home, learn, history, progress, profile) in the
 * learner's language. Session words live in features/study/labels.ts.
 */
import type { BuddyLanguage } from '@/types';

export type Strings = {
  greet: (part: 'morning' | 'afternoon' | 'evening', name: string) => string;
  nav: { home: string; history: string; progress: string; profile: string };
  streak: (n: number) => string;
  streakLabel: string;
  weekLabel: string;
  ideasLabel: string;
  studyTitle: string;
  studyBody: string;
  talkTitle: string;
  talkBody: string;
  startNow: string;
  quickTopics: string;
  continueTitle: string;
  continueCta: string;
  ideasOf: (n: number, total: number) => string;
  moodTitle: string;
  moods: { id: string; label: string }[];
  learnTitle: string;
  learnPlaceholder: string;
  learnStart: string;
  yourTopics: string;
  suggestions: string;
  historyTitle: string;
  historyEmpty: string;
  today: string;
  yesterday: string;
  justTalk: string;
  noTopic: string;
  studyAgain: string;
  sessionNotFound: string;
  keyIdeas: string;
  status: { understood: string; partial: string; gap: string; unseen: string };
  progressTitle: string;
  last14: string;
  sessionsTotal: string;
  topicsLearned: string;
  progressEmpty: string;
  profileTitle: string;
  language: string;
  voice: string;
  voices: { kavya: string; shubh: string };
  helpTitle: string;
  helpBody: string;
  helpCall: string;
  signOut: string;
  loading: string;
  back: string;
  conceptsHelp: string;
  forYou: string;
  continueNext: (concept: string) => string;
  levels: { just_started: string; getting_there: string; confident: string };
  moodNames: Record<'calm' | 'happy' | 'tired' | 'bored' | 'stressed' | 'anxious' | 'frustrated' | 'sad', string>;
  insightsTitle: string;
  feelingTitle: string;
  feelingEmpty: string;
  feelingSummary: (common: string, trend: 'up' | 'down' | 'steady') => string;
  learningTitle: string;
  privateNote: string;
  helpNudge: string;
  heroAsk: string;
  gardenTitle: string;
  gardenHelp: string;
  styles: { learn: string; learnHint: string; teach: string; teachHint: string; teachStart: string; teachPage: string };
  page: { title: string; body: string; take: string; reading: string; found: string; start: string; retake: string };
  streakLine: (days: number, week: number, concepts: number) => string;
  noteNext: string;
};

const en: Strings = {
  greet: (part, name) => `Good ${part}${name ? `, ${name}` : ''}`,
  nav: { home: 'Home', history: 'History', progress: 'Insights', profile: 'Me' },
  streak: (n) => (n === 1 ? '1 day' : `${n} days`),
  streakLabel: 'Streak',
  weekLabel: 'This week',
  ideasLabel: 'Concepts',
  studyTitle: 'Study with me',
  studyBody: 'Pick a topic. I explain it simply, ask gentle questions and help you get it.',
  talkTitle: 'Just talk',
  talkBody: 'Stressed, bored or just want company? Talk about anything. I listen.',
  startNow: 'Start',
  quickTopics: 'Quick start',
  continueTitle: 'Pick up where you left off',
  continueCta: 'Continue',
  ideasOf: (n, total) => `${n} of ${total} concepts`,
  moodTitle: 'How are you feeling?',
  moods: [
    { id: 'stressed', label: 'Stressed' },
    { id: 'exam', label: 'Worried about exams' },
    { id: 'bored', label: 'Bored' },
    { id: 'tired', label: 'Tired' },
    { id: 'happy', label: 'Happy' },
  ],
  learnTitle: 'What do you want to learn?',
  learnPlaceholder: 'Type any topic, e.g. the water cycle',
  learnStart: 'Start studying',
  yourTopics: 'Your topics',
  suggestions: 'Ideas',
  historyTitle: 'Your sessions',
  historyEmpty: 'No sessions yet. Start one from Home.',
  today: 'Today',
  yesterday: 'Yesterday',
  justTalk: 'Just talk',
  noTopic: 'Open chat',
  studyAgain: 'Study this again',
  sessionNotFound: 'Session not found.',
  keyIdeas: 'Key concepts',
  status: { understood: 'Got it', partial: 'Almost', gap: 'Still working', unseen: 'Not yet' },
  progressTitle: 'Your learning journey',
  last14: 'Last 14 days',
  sessionsTotal: 'Sessions',
  topicsLearned: 'Topics',
  progressEmpty: 'Your topics will show up here after your first study session.',
  conceptsHelp: 'Concepts are the key points of a topic. Your buddy checks, gently, which ones you have understood.',
  forYou: 'For you',
  continueNext: (c) => `Next up: ${c}`,
  levels: { just_started: 'Just started', getting_there: 'Getting there', confident: 'Confident' },
  moodNames: { calm: 'calm', happy: 'happy', tired: 'tired', bored: 'bored', stressed: 'stressed', anxious: 'anxious', frustrated: 'frustrated', sad: 'low' },
  insightsTitle: 'Insights',
  feelingTitle: "How you've been feeling",
  feelingEmpty: 'After a few sessions, your buddy will show how you have been feeling here.',
  feelingSummary: (common, trend) =>
    trend === 'up'
      ? 'Things look brighter for you lately. Nice!'
      : trend === 'down'
        ? 'The last few days seem a bit heavier. Talking about it might help.'
        : `You've mostly seemed ${common} lately.`,
  learningTitle: 'Learning level',
  privateNote: "Only you can see this. It's your buddy's gentle read, not a diagnosis.",
  heroAsk: 'What shall we do today?',
  gardenTitle: 'Your garden',
  gardenHelp: 'Every topic is a plant. Each leaf is a concept: it turns green when you understand it, and the plant flowers when you know the whole topic.',
  styles: {
    learn: 'Learn it',
    learnHint: 'I explain simply and ask small questions.',
    teach: 'Test your knowledge',
    teachHint: "You're the teacher. Explain it to me and I'll ask \"but why?\"",
    teachStart: 'Start teaching',
    teachPage: 'Test me on this page',
  },
  page: {
    title: 'Study a page from your book',
    body: "Take a photo of a textbook page. I'll read it and we'll go through it together.",
    take: 'Take a photo',
    reading: 'Reading your page…',
    found: 'What this page is about',
    start: 'Study this page',
    retake: 'Another photo',
  },
  streakLine: (d, w, c) => `${d} day${d === 1 ? '' : 's'} in a row · ${w} this week · ${c} concepts`,
  noteNext: 'note to self',
  helpNudge: 'Some days have felt really heavy. You are not alone: talk to someone you trust, or call Tele-MANAS 14416.',
  profileTitle: 'Me',
  language: 'Language',
  voice: "Buddy's voice",
  voices: { kavya: 'Kavya (female)', shubh: 'Shubh (male)' },
  helpTitle: 'Help & safety',
  helpBody: 'Your buddy is a friend, not a counsellor. If things feel too heavy, talk to someone you trust or call Tele-MANAS (free, 24x7). In an emergency, call 112.',
  helpCall: 'Call Tele-MANAS 14416',
  signOut: 'Sign out',
  loading: 'Loading…',
  back: 'Back',
};

const te: Strings = {
  ...en,
  greet: (part, name) =>
    `${{ morning: 'శుభోదయం', afternoon: 'నమస్కారం', evening: 'శుభ సాయంత్రం' }[part]}${name ? `, ${name}` : ''}`,
  nav: { home: 'హోమ్', history: 'చరిత్ర', progress: 'ప్రగతి', profile: 'నేను' },
  streak: (n) => `${n} రోజులు`,
  streakLabel: 'వరుసగా',
  weekLabel: 'ఈ వారం',
  ideasLabel: 'కాన్సెప్ట్స్',
  studyTitle: 'నాతో చదువు',
  studyBody: 'ఒక టాపిక్ ఎంచుకో. నేను సింపుల్ గా చెప్పి, చిన్న ప్రశ్నలతో అర్థమయ్యేలా చేస్తాను.',
  talkTitle: 'ఊరికే మాట్లాడదాం',
  talkBody: 'స్ట్రెస్ గా ఉందా, బోర్ కొడుతోందా? ఏదైనా మాట్లాడు. నేను వింటాను.',
  startNow: 'మొదలుపెట్టు',
  quickTopics: 'త్వరగా మొదలుపెట్టు',
  continueTitle: 'ఆపిన చోటు నుంచి కొనసాగిద్దాం',
  continueCta: 'కొనసాగించు',
  ideasOf: (n, total) => `${total}లో ${n} కాన్సెప్ట్స్`,
  moodTitle: 'ఇప్పుడు ఎలా ఉంది?',
  moods: [
    { id: 'stressed', label: 'స్ట్రెస్ గా ఉంది' },
    { id: 'exam', label: 'ఎగ్జామ్ భయం' },
    { id: 'bored', label: 'బోర్ కొడుతోంది' },
    { id: 'tired', label: 'అలసటగా ఉంది' },
    { id: 'happy', label: 'హ్యాపీగా ఉంది' },
  ],
  learnTitle: 'ఏం నేర్చుకోవాలనుకుంటున్నావు?',
  learnPlaceholder: 'ఏదైనా టాపిక్ టైప్ చేయి, ఉదా: నీటి చక్రం',
  learnStart: 'చదువు మొదలుపెట్టు',
  yourTopics: 'నీ టాపిక్స్',
  suggestions: 'ఐడియాలు',
  historyTitle: 'నీ సెషన్లు',
  historyEmpty: 'ఇంకా సెషన్లు లేవు. హోమ్ నుంచి మొదలుపెట్టు.',
  today: 'ఈ రోజు',
  yesterday: 'నిన్న',
  justTalk: 'ఊరికే మాట్లాడాం',
  noTopic: 'ఓపెన్ చాట్',
  studyAgain: 'మళ్ళీ చదువుదాం',
  sessionNotFound: 'సెషన్ దొరకలేదు.',
  keyIdeas: 'ముఖ్యమైన కాన్సెప్ట్స్',
  status: { understood: 'అర్థమైంది', partial: 'దాదాపు', gap: 'ఇంకా ప్రయత్నిస్తున్నాం', unseen: 'ఇంకా లేదు' },
  progressTitle: 'నీ నేర్చుకునే ప్రయాణం',
  last14: 'గత 14 రోజులు',
  sessionsTotal: 'సెషన్లు',
  topicsLearned: 'టాపిక్స్',
  progressEmpty: 'నీ మొదటి స్టడీ సెషన్ తర్వాత నీ టాపిక్స్ ఇక్కడ కనిపిస్తాయి.',
  conceptsHelp: 'కాన్సెప్ట్స్ అంటే ఒక టాపిక్ లోని ముఖ్యమైన పాయింట్లు. నీకు ఏవి అర్థమయ్యాయో నీ బడ్డీ మెల్లగా చెక్ చేస్తుంది.',
  forYou: 'నీ కోసం',
  continueNext: (c) => `తర్వాత: ${c}`,
  levels: { just_started: 'ఇప్పుడే మొదలుపెట్టాం', getting_there: 'దాదాపు వచ్చేసింది', confident: 'బాగా వచ్చింది' },
  moodNames: { calm: 'ప్రశాంతంగా', happy: 'హ్యాపీగా', tired: 'అలసటగా', bored: 'బోర్ గా', stressed: 'స్ట్రెస్ గా', anxious: 'కంగారుగా', frustrated: 'చిరాకుగా', sad: 'బాధగా' },
  insightsTitle: 'ప్రగతి',
  feelingTitle: 'నువ్వు ఎలా ఉన్నావు',
  feelingEmpty: 'కొన్ని సెషన్ల తర్వాత, నువ్వు ఎలా ఫీల్ అవుతున్నావో ఇక్కడ కనిపిస్తుంది.',
  feelingSummary: (common, trend) =>
    trend === 'up'
      ? 'ఈ మధ్య నువ్వు బెటర్ గా ఉన్నట్టు అనిపిస్తోంది. సూపర్!'
      : trend === 'down'
        ? 'గత కొన్ని రోజులు కొంచెం భారంగా ఉన్నట్టుంది. దాని గురించి మాట్లాడితే హెల్ప్ అవుతుంది.'
        : `ఈ మధ్య ఎక్కువగా ${common} ఉన్నావు.`,
  learningTitle: 'నేర్చుకునే స్థాయి',
  privateNote: 'ఇది నీకు మాత్రమే కనిపిస్తుంది. ఇది నీ బడ్డీ అభిప్రాయం మాత్రమే, డయాగ్నోసిస్ కాదు.',
  heroAsk: 'ఈ రోజు ఏం చేద్దాం?',
  gardenTitle: 'నీ తోట',
  gardenHelp: 'ప్రతి టాపిక్ ఒక మొక్క. ప్రతి ఆకు ఒక కాన్సెప్ట్: అర్థమైతే పచ్చగా మారుతుంది, టాపిక్ మొత్తం వస్తే పువ్వు పూస్తుంది.',
  styles: {
    learn: 'నేర్చుకో',
    learnHint: 'నేను సింపుల్ గా చెప్పి, చిన్న ప్రశ్నలు అడుగుతా.',
    teach: 'నీ నాలెడ్జ్ టెస్ట్ చేసుకో',
    teachHint: 'నువ్వే టీచర్. నాకు చెప్పు, నేను "ఎందుకు?" అని అడుగుతా.',
    teachStart: 'చెప్పడం మొదలుపెట్టు',
    teachPage: 'ఈ పేజీపై నన్ను టెస్ట్ చేయి',
  },
  page: {
    title: 'నీ బుక్ లోని పేజీ చదువుదాం',
    body: 'టెక్స్ట్ బుక్ పేజీ ఫోటో తీయి. నేను చదివి, మనిద్దరం కలిసి అర్థం చేసుకుందాం.',
    take: 'ఫోటో తీయి',
    reading: 'నీ పేజీ చదువుతున్నా…',
    found: 'ఈ పేజీలో ఏముంది',
    start: 'ఈ పేజీ చదువుదాం',
    retake: 'ఇంకో ఫోటో',
  },
  streakLine: (d, w, c) => `వరుసగా ${d} రోజులు · ఈ వారం ${w} · ${c} కాన్సెప్ట్స్`,
  noteNext: 'గుర్తుంచుకో',
  helpNudge: 'కొన్ని రోజులు చాలా భారంగా అనిపించాయి. నువ్వు ఒంటరివి కాదు: నమ్మే వాళ్ళతో మాట్లాడు, లేదా Tele-MANAS 14416 కి కాల్ చేయి.',
  profileTitle: 'నేను',
  language: 'భాష',
  voice: 'బడ్డీ గొంతు',
  voices: { kavya: 'కావ్య (ఆడ గొంతు)', shubh: 'శుభ్ (మగ గొంతు)' },
  helpTitle: 'సహాయం & భద్రత',
  helpBody: 'నీ బడ్డీ ఒక ఫ్రెండ్ మాత్రమే, కౌన్సిలర్ కాదు. చాలా భారంగా అనిపిస్తే, నువ్వు నమ్మే వాళ్ళతో మాట్లాడు లేదా Tele-MANAS కి కాల్ చేయి (ఉచితం, 24x7). అత్యవసరమైతే 112.',
  helpCall: 'Tele-MANAS 14416 కి కాల్ చేయి',
  signOut: 'సైన్ అవుట్',
  loading: 'లోడ్ అవుతోంది…',
  back: 'వెనక్కి',
};

const ml: Strings = {
  ...en,
  greet: (part, name) =>
    `${{ morning: 'സുപ്രഭാതം', afternoon: 'നമസ്കാരം', evening: 'ശുഭസായാഹ്നം' }[part]}${name ? `, ${name}` : ''}`,
  nav: { home: 'ഹോം', history: 'ചരിത്രം', progress: 'പുരോഗതി', profile: 'ഞാൻ' },
  streak: (n) => `${n} ദിവസം`,
  streakLabel: 'തുടർച്ചയായി',
  weekLabel: 'ഈ ആഴ്ച',
  ideasLabel: 'കൺസെപ്റ്റുകൾ',
  studyTitle: 'എന്റെ കൂടെ പഠിക്കാം',
  studyBody: 'ഒരു വിഷയം തിരഞ്ഞെടുക്കൂ. ഞാൻ ലളിതമായി പറഞ്ഞു തന്ന്, ചെറിയ ചോദ്യങ്ങളിലൂടെ മനസ്സിലാക്കി തരാം.',
  talkTitle: 'വെറുതെ സംസാരിക്കാം',
  talkBody: 'ടെൻഷനാണോ, ബോറടിക്കുന്നോ? എന്തും പറയാം. ഞാൻ കേൾക്കാം.',
  startNow: 'തുടങ്ങാം',
  quickTopics: 'വേഗം തുടങ്ങാം',
  continueTitle: 'നിർത്തിയിടത്തു നിന്ന് തുടരാം',
  continueCta: 'തുടരാം',
  ideasOf: (n, total) => `${total}ൽ ${n} കൺസെപ്റ്റുകൾ`,
  moodTitle: 'ഇപ്പോ എങ്ങനെയുണ്ട്?',
  moods: [
    { id: 'stressed', label: 'ടെൻഷനാണ്' },
    { id: 'exam', label: 'പരീക്ഷാ പേടി' },
    { id: 'bored', label: 'ബോറടിക്കുന്നു' },
    { id: 'tired', label: 'ക്ഷീണമാണ്' },
    { id: 'happy', label: 'സന്തോഷമാണ്' },
  ],
  learnTitle: 'എന്ത് പഠിക്കണം?',
  learnPlaceholder: 'ഏത് വിഷയവും ടൈപ്പ് ചെയ്യൂ, ഉദാ: ജലചക്രം',
  learnStart: 'പഠിക്കാൻ തുടങ്ങാം',
  yourTopics: 'നിന്റെ വിഷയങ്ങൾ',
  suggestions: 'ആശയങ്ങൾ',
  historyTitle: 'നിന്റെ സെഷനുകൾ',
  historyEmpty: 'ഇതുവരെ സെഷനുകൾ ഇല്ല. ഹോമിൽ നിന്ന് തുടങ്ങൂ.',
  today: 'ഇന്ന്',
  yesterday: 'ഇന്നലെ',
  justTalk: 'വെറുതെ സംസാരിച്ചു',
  noTopic: 'തുറന്ന സംസാരം',
  studyAgain: 'വീണ്ടും പഠിക്കാം',
  sessionNotFound: 'സെഷൻ കണ്ടെത്തിയില്ല.',
  keyIdeas: 'പ്രധാന കൺസെപ്റ്റുകൾ',
  status: { understood: 'മനസ്സിലായി', partial: 'ഏതാണ്ട്', gap: 'ഇനിയും ശ്രമിക്കാം', unseen: 'ഇതുവരെ ഇല്ല' },
  progressTitle: 'നിന്റെ പഠന യാത്ര',
  last14: 'കഴിഞ്ഞ 14 ദിവസം',
  sessionsTotal: 'സെഷനുകൾ',
  topicsLearned: 'വിഷയങ്ങൾ',
  progressEmpty: 'ആദ്യത്തെ പഠന സെഷനു ശേഷം നിന്റെ വിഷയങ്ങൾ ഇവിടെ കാണാം.',
  conceptsHelp: 'കൺസെപ്റ്റുകൾ എന്നാൽ ഒരു വിഷയത്തിലെ പ്രധാന കാര്യങ്ങൾ. ഏതൊക്കെ നിനക്ക് മനസ്സിലായെന്ന് കൂട്ടുകാരൻ പതുക്കെ നോക്കും.',
  forYou: 'നിനക്കായി',
  continueNext: (c) => `അടുത്തത്: ${c}`,
  levels: { just_started: 'തുടങ്ങിയതേയുള്ളൂ', getting_there: 'ഏതാണ്ട് ആയി', confident: 'നന്നായി അറിയാം' },
  moodNames: { calm: 'ശാന്തമായി', happy: 'സന്തോഷത്തോടെ', tired: 'ക്ഷീണിതനായി', bored: 'ബോറടിച്ച്', stressed: 'ടെൻഷനോടെ', anxious: 'പേടിയോടെ', frustrated: 'ദേഷ്യത്തോടെ', sad: 'വിഷമത്തോടെ' },
  insightsTitle: 'പുരോഗതി',
  feelingTitle: 'നീ എങ്ങനെയുണ്ടായിരുന്നു',
  feelingEmpty: 'കുറച്ച് സെഷനുകൾക്ക് ശേഷം, നിനക്ക് എങ്ങനെ തോന്നുന്നുവെന്ന് ഇവിടെ കാണാം.',
  feelingSummary: (common, trend) =>
    trend === 'up'
      ? 'ഈയിടെ നിനക്ക് കുറച്ചുകൂടി നല്ലതായി തോന്നുന്നു. അടിപൊളി!'
      : trend === 'down'
        ? 'കഴിഞ്ഞ കുറച്ച് ദിവസങ്ങൾ കുറച്ച് ഭാരമുള്ളതായി തോന്നുന്നു. അതേക്കുറിച്ച് സംസാരിച്ചാൽ ആശ്വാസമാകും.'
        : `ഈയിടെ കൂടുതലും ${common} ആയിരുന്നു.`,
  learningTitle: 'പഠന നില',
  privateNote: 'ഇത് നിനക്ക് മാത്രമേ കാണാനാകൂ. ഇത് കൂട്ടുകാരന്റെ ഒരു തോന്നൽ മാത്രം, രോഗനിർണയമല്ല.',
  heroAsk: 'ഇന്ന് എന്താ ചെയ്യേണ്ടത്?',
  gardenTitle: 'നിന്റെ തോട്ടം',
  gardenHelp: 'ഓരോ ടോപിക്കും ഒരു ചെടി. ഓരോ ഇലയും ഒരു കൺസെപ്റ്റ്: മനസ്സിലായാൽ പച്ചയാകും, ടോപിക് മുഴുവൻ അറിഞ്ഞാൽ പൂവിടും.',
  styles: {
    learn: 'പഠിക്കാം',
    learnHint: 'ഞാൻ ലളിതമായി പറഞ്ഞ് ചെറിയ ചോദ്യങ്ങൾ ചോദിക്കും.',
    teach: 'നിന്റെ അറിവ് പരീക്ഷിക്ക്',
    teachHint: 'നീയാണ് ടീച്ചർ. എനിക്ക് പറഞ്ഞു താ, ഞാൻ "എന്തുകൊണ്ട്?" എന്ന് ചോദിക്കും.',
    teachStart: 'പഠിപ്പിച്ചു തുടങ്ങ്',
    teachPage: 'ഈ പേജിൽ എന്നെ ടെസ്റ്റ് ചെയ്യ്',
  },
  page: {
    title: 'നിന്റെ പുസ്തകത്തിലെ ഒരു പേജ് പഠിക്കാം',
    body: 'ടെക്സ്റ്റ്ബുക്ക് പേജിന്റെ ഫോട്ടോ എടുക്ക്. ഞാൻ വായിച്ചിട്ട് നമുക്ക് ഒരുമിച്ച് പഠിക്കാം.',
    take: 'ഫോട്ടോ എടുക്ക്',
    reading: 'നിന്റെ പേജ് വായിക്കുന്നു…',
    found: 'ഈ പേജിൽ എന്താണ്',
    start: 'ഈ പേജ് പഠിക്കാം',
    retake: 'വേറൊരു ഫോട്ടോ',
  },
  streakLine: (d, w, c) => `തുടർച്ചയായി ${d} ദിവസം · ഈ ആഴ്ച ${w} · ${c} കൺസെപ്റ്റുകൾ`,
  noteNext: 'ഓർമ്മയ്ക്ക്',
  helpNudge: 'ചില ദിവസങ്ങൾ വല്ലാതെ ഭാരമുള്ളതായി തോന്നി. നീ ഒറ്റയ്ക്കല്ല: വിശ്വസിക്കുന്ന ആരോടെങ്കിലും സംസാരിക്കൂ, അല്ലെങ്കിൽ Tele-MANAS 14416 ൽ വിളിക്കൂ.',
  profileTitle: 'ഞാൻ',
  language: 'ഭാഷ',
  voice: 'കൂട്ടുകാരന്റെ ശബ്ദം',
  voices: { kavya: 'കാവ്യ (സ്ത്രീ ശബ്ദം)', shubh: 'ശുഭ് (പുരുഷ ശബ്ദം)' },
  helpTitle: 'സഹായവും സുരക്ഷയും',
  helpBody: 'നിന്റെ കൂട്ടുകാരൻ ഒരു സുഹൃത്ത് മാത്രമാണ്, കൗൺസിലർ അല്ല. വല്ലാതെ ഭാരം തോന്നിയാൽ, വിശ്വസിക്കുന്ന ആരോടെങ്കിലും സംസാരിക്കൂ, അല്ലെങ്കിൽ Tele-MANAS ൽ വിളിക്കൂ (സൗജന്യം, 24x7). അടിയന്തരമെങ്കിൽ 112.',
  helpCall: 'Tele-MANAS 14416 ൽ വിളിക്കൂ',
  signOut: 'സൈൻ ഔട്ട്',
  loading: 'ലോഡ് ചെയ്യുന്നു…',
  back: 'തിരികെ',
};

const ta: Strings = {
  ...en,
  greet: (part, name) =>
    `${{ morning: 'காலை வணக்கம்', afternoon: 'வணக்கம்', evening: 'மாலை வணக்கம்' }[part]}${name ? `, ${name}` : ''}`,
  nav: { home: 'முகப்பு', history: 'வரலாறு', progress: 'முன்னேற்றம்', profile: 'நான்' },
  streak: (n) => `${n} நாட்கள்`,
  streakLabel: 'தொடர்ச்சியா',
  weekLabel: 'இந்த வாரம்',
  ideasLabel: 'கான்செப்ட்ஸ்',
  studyTitle: 'என்கூட படி',
  studyBody: 'ஒரு டாபிக் தேர்ந்தெடு. நான் சிம்பிளா சொல்லி, சின்ன கேள்விகளால புரிய வைக்கிறேன்.',
  talkTitle: 'சும்மா பேசலாம்',
  talkBody: 'ஸ்ட்ரெஸ்ஸா இருக்கா, போர் அடிக்குதா? எதுவானாலும் பேசு. நான் கேக்கறேன்.',
  startNow: 'ஆரம்பி',
  quickTopics: 'சீக்கிரம் ஆரம்பி',
  continueTitle: 'விட்ட இடத்துல இருந்து தொடரலாம்',
  continueCta: 'தொடரு',
  ideasOf: (n, total) => `${total}ல ${n} கான்செப்ட்ஸ்`,
  moodTitle: 'இப்போ எப்படி இருக்க?',
  moods: [
    { id: 'stressed', label: 'ஸ்ட்ரெஸ்ஸா இருக்கு' },
    { id: 'exam', label: 'எக்ஸாம் பயம்' },
    { id: 'bored', label: 'போர் அடிக்குது' },
    { id: 'tired', label: 'சோர்வா இருக்கு' },
    { id: 'happy', label: 'சந்தோஷமா இருக்கு' },
  ],
  learnTitle: 'என்ன கத்துக்கணும்?',
  learnPlaceholder: 'ஏதாவது டாபிக் டைப் பண்ணு, உதா: நீர் சுழற்சி',
  learnStart: 'படிக்க ஆரம்பி',
  yourTopics: 'உன் டாபிக்ஸ்',
  suggestions: 'ஐடியாக்கள்',
  historyTitle: 'உன் செஷன்கள்',
  historyEmpty: 'இன்னும் செஷன் இல்ல. முகப்புல இருந்து ஆரம்பி.',
  today: 'இன்னைக்கு',
  yesterday: 'நேத்து',
  justTalk: 'சும்மா பேசினோம்',
  noTopic: 'ஓப்பன் சாட்',
  studyAgain: 'திரும்ப படிக்கலாம்',
  sessionNotFound: 'செஷன் கிடைக்கல.',
  keyIdeas: 'முக்கியமான கான்செப்ட்ஸ்',
  status: { understood: 'புரிஞ்சுது', partial: 'கிட்டத்தட்ட', gap: 'இன்னும் முயற்சி', unseen: 'இன்னும் இல்ல' },
  progressTitle: 'உன் கத்துக்கற பயணம்',
  last14: 'கடைசி 14 நாட்கள்',
  sessionsTotal: 'செஷன்கள்',
  topicsLearned: 'டாபிக்ஸ்',
  progressEmpty: 'உன் முதல் படிப்பு செஷனுக்கு அப்புறம் உன் டாபிக்ஸ் இங்க வரும்.',
  conceptsHelp: 'கான்செப்ட்ஸ்னா ஒரு டாபிக்கோட முக்கியமான பாயிண்ட்ஸ். உனக்கு எது புரிஞ்சுதுன்னு உன் பட்டி மெதுவா செக் பண்ணும்.',
  forYou: 'உனக்காக',
  continueNext: (c) => `அடுத்து: ${c}`,
  levels: { just_started: 'இப்போ தான் ஆரம்பம்', getting_there: 'கிட்டத்தட்ட வந்துடுச்சு', confident: 'நல்லா தெரியும்' },
  moodNames: { calm: 'அமைதியா', happy: 'சந்தோஷமா', tired: 'சோர்வா', bored: 'போரா', stressed: 'ஸ்ட்ரெஸ்ஸா', anxious: 'பதட்டமா', frustrated: 'எரிச்சலா', sad: 'சோகமா' },
  insightsTitle: 'முன்னேற்றம்',
  feelingTitle: 'நீ எப்படி இருக்க',
  feelingEmpty: 'சில செஷன்களுக்கு அப்புறம், நீ எப்படி ஃபீல் பண்றேன்னு இங்க தெரியும்.',
  feelingSummary: (common, trend) =>
    trend === 'up'
      ? 'இப்போ கொஞ்ச நாளா நீ நல்லா இருக்க மாதிரி தெரியுது. சூப்பர்!'
      : trend === 'down'
        ? 'கடைசி சில நாட்கள் கொஞ்சம் பாரமா இருந்த மாதிரி இருக்கு. அதைப் பத்தி பேசினா உதவும்.'
        : `இப்போ பெரும்பாலும் ${common} இருக்க.`,
  learningTitle: 'கத்துக்கற நிலை',
  privateNote: 'இது உனக்கு மட்டும் தான் தெரியும். இது உன் பட்டியோட கருத்து மட்டும், டயக்னோசிஸ் இல்ல.',
  heroAsk: 'இன்னைக்கு என்ன பண்ணலாம்?',
  gardenTitle: 'உன் தோட்டம்',
  gardenHelp: 'ஒவ்வொரு டாபிக்கும் ஒரு செடி. ஒவ்வொரு இலையும் ஒரு கான்செப்ட்: புரிஞ்சா பச்சையாகும், டாபிக் முழுசா தெரிஞ்சா பூ பூக்கும்.',
  styles: {
    learn: 'கத்துக்கோ',
    learnHint: 'நான் சிம்பிளா சொல்லி, சின்ன கேள்விகள் கேப்பேன்.',
    teach: 'உன் அறிவை டெஸ்ட் பண்ணு',
    teachHint: 'நீ தான் டீச்சர். எனக்கு சொல்லு, நான் "ஏன்?"னு கேப்பேன்.',
    teachStart: 'சொல்லித் தர ஆரம்பி',
    teachPage: 'இந்த பக்கத்துல என்னை டெஸ்ட் பண்ணு',
  },
  page: {
    title: 'உன் புக்ல இருந்து ஒரு பக்கம் படிக்கலாம்',
    body: 'டெக்ஸ்ட் புக் பக்கத்தை ஃபோட்டோ எடு. நான் படிச்சிட்டு, நாம சேர்ந்து புரிஞ்சுக்கலாம்.',
    take: 'ஃபோட்டோ எடு',
    reading: 'உன் பக்கத்தை படிக்கிறேன்…',
    found: 'இந்த பக்கத்துல என்ன இருக்கு',
    start: 'இந்த பக்கம் படிக்கலாம்',
    retake: 'இன்னொரு ஃபோட்டோ',
  },
  streakLine: (d, w, c) => `தொடர்ச்சியா ${d} நாட்கள் · இந்த வாரம் ${w} · ${c} கான்செப்ட்ஸ்`,
  noteNext: 'ஞாபகத்துக்கு',
  helpNudge: 'சில நாட்கள் ரொம்ப பாரமா இருந்திருக்கு. நீ தனியா இல்ல: நம்புறவங்ககிட்ட பேசு, இல்லனா Tele-MANAS 14416 க்கு கால் பண்ணு.',
  profileTitle: 'நான்',
  language: 'மொழி',
  voice: 'பட்டியோட குரல்',
  voices: { kavya: 'காவ்யா (பெண் குரல்)', shubh: 'ஷுப் (ஆண் குரல்)' },
  helpTitle: 'உதவி & பாதுகாப்பு',
  helpBody: 'உன் பட்டி ஒரு ஃப்ரெண்ட் மட்டும் தான், கவுன்சிலர் இல்ல. ரொம்ப பாரமா இருந்தா, நம்புறவங்ககிட்ட பேசு இல்லனா Tele-MANAS க்கு கால் பண்ணு (இலவசம், 24x7). அவசரம்னா 112.',
  helpCall: 'Tele-MANAS 14416 க்கு கால் பண்ணு',
  signOut: 'சைன் அவுட்',
  loading: 'லோட் ஆகுது…',
  back: 'பின்னால',
};

const hi: Strings = {
  ...en,
  greet: (part, name) =>
    `${{ morning: 'सुप्रभात', afternoon: 'नमस्ते', evening: 'शुभ संध्या' }[part]}${name ? `, ${name}` : ''}`,
  nav: { home: 'होम', history: 'हिस्ट्री', progress: 'प्रगति', profile: 'मैं' },
  streak: (n) => `${n} दिन`,
  streakLabel: 'लगातार',
  weekLabel: 'इस हफ़्ते',
  ideasLabel: 'कॉन्सेप्ट्स',
  studyTitle: 'मेरे साथ पढ़ो',
  studyBody: 'कोई टॉपिक चुनो। मैं आसान तरीके से समझाऊँगा और छोटे सवालों से समझने में मदद करूँगा।',
  talkTitle: 'बस बात करें',
  talkBody: 'स्ट्रेस है, बोर हो रहे हो? कुछ भी बात करो। मैं सुनूँगा।',
  startNow: 'शुरू करो',
  quickTopics: 'जल्दी शुरू करो',
  continueTitle: 'जहाँ छोड़ा था वहीं से',
  continueCta: 'जारी रखो',
  ideasOf: (n, total) => `${total} में से ${n} कॉन्सेप्ट्स`,
  moodTitle: 'अभी कैसा लग रहा है?',
  moods: [
    { id: 'stressed', label: 'स्ट्रेस है' },
    { id: 'exam', label: 'एग्ज़ाम का डर' },
    { id: 'bored', label: 'बोर हो रहा हूँ' },
    { id: 'tired', label: 'थका हुआ हूँ' },
    { id: 'happy', label: 'खुश हूँ' },
  ],
  learnTitle: 'क्या सीखना है?',
  learnPlaceholder: 'कोई भी टॉपिक लिखो, जैसे: जल चक्र',
  learnStart: 'पढ़ाई शुरू करो',
  yourTopics: 'तुम्हारे टॉपिक्स',
  suggestions: 'आइडियाज़',
  historyTitle: 'तुम्हारे सेशन',
  historyEmpty: 'अभी कोई सेशन नहीं। होम से शुरू करो।',
  today: 'आज',
  yesterday: 'कल',
  justTalk: 'बस बात की',
  noTopic: 'खुली बातचीत',
  studyAgain: 'फिर से पढ़ें',
  sessionNotFound: 'सेशन नहीं मिला।',
  keyIdeas: 'ज़रूरी कॉन्सेप्ट्स',
  status: { understood: 'समझ आया', partial: 'लगभग', gap: 'अभी कोशिश जारी', unseen: 'अभी नहीं' },
  progressTitle: 'तुम्हारा सीखने का सफ़र',
  last14: 'पिछले 14 दिन',
  sessionsTotal: 'सेशन',
  topicsLearned: 'टॉपिक्स',
  progressEmpty: 'पहले स्टडी सेशन के बाद तुम्हारे टॉपिक्स यहाँ दिखेंगे।',
  conceptsHelp: 'कॉन्सेप्ट्स मतलब किसी टॉपिक के ज़रूरी पॉइंट्स। तुम्हें कौन से समझ आए, ये तुम्हारा बडी धीरे से चेक करता है।',
  forYou: 'तुम्हारे लिए',
  continueNext: (c) => `अगला: ${c}`,
  levels: { just_started: 'अभी शुरू किया', getting_there: 'लगभग आ गया', confident: 'अच्छे से आता है' },
  moodNames: { calm: 'शांत', happy: 'खुश', tired: 'थके हुए', bored: 'बोर', stressed: 'स्ट्रेस में', anxious: 'घबराए हुए', frustrated: 'चिढ़े हुए', sad: 'उदास' },
  insightsTitle: 'प्रगति',
  feelingTitle: 'तुम कैसा महसूस कर रहे हो',
  feelingEmpty: 'कुछ सेशन के बाद, तुम कैसा महसूस कर रहे हो वो यहाँ दिखेगा।',
  feelingSummary: (common, trend) =>
    trend === 'up'
      ? 'आजकल तुम पहले से बेहतर लग रहे हो। बढ़िया!'
      : trend === 'down'
        ? 'पिछले कुछ दिन थोड़े भारी लगे। इसके बारे में बात करने से मदद मिल सकती है।'
        : `आजकल ज़्यादातर तुम ${common} लगे।`,
  learningTitle: 'सीखने का लेवल',
  privateNote: 'ये सिर्फ़ तुम्हें दिखता है। ये तुम्हारे बडी की राय है, कोई डायग्नोसिस नहीं।',
  heroAsk: 'आज क्या करें?',
  gardenTitle: 'तुम्हारा बगीचा',
  gardenHelp: 'हर टॉपिक एक पौधा है। हर पत्ता एक कॉन्सेप्ट: समझ आने पर हरा हो जाता है, और पूरा टॉपिक आने पर फूल खिलता है।',
  styles: {
    learn: 'सीखो',
    learnHint: 'मैं आसान तरीके से समझाऊँगा और छोटे सवाल पूछूँगा।',
    teach: 'अपना ज्ञान परखो',
    teachHint: 'आज तुम टीचर हो। मुझे समझाओ, मैं पूछूँगा "पर क्यों?"',
    teachStart: 'सिखाना शुरू करो',
    teachPage: 'इस पेज पर मुझे टेस्ट करो',
  },
  page: {
    title: 'अपनी किताब का एक पेज पढ़ें',
    body: 'टेक्स्टबुक के पेज की फ़ोटो लो। मैं पढ़ूँगा और फिर हम साथ में समझेंगे।',
    take: 'फ़ोटो लो',
    reading: 'तुम्हारा पेज पढ़ रहा हूँ…',
    found: 'इस पेज में क्या है',
    start: 'ये पेज पढ़ें',
    retake: 'दूसरी फ़ोटो',
  },
  streakLine: (d, w, c) => `लगातार ${d} दिन · इस हफ़्ते ${w} · ${c} कॉन्सेप्ट्स`,
  noteNext: 'याद रखना',
  helpNudge: 'कुछ दिन बहुत भारी लगे हैं। तुम अकेले नहीं हो: किसी भरोसे वाले से बात करो, या Tele-MANAS 14416 पर कॉल करो।',
  profileTitle: 'मैं',
  language: 'भाषा',
  voice: 'बडी की आवाज़',
  voices: { kavya: 'काव्या (महिला आवाज़)', shubh: 'शुभ (पुरुष आवाज़)' },
  helpTitle: 'मदद और सुरक्षा',
  helpBody: 'तुम्हारा बडी एक दोस्त है, काउंसलर नहीं। अगर बहुत भारी लगे, तो किसी भरोसे वाले से बात करो या Tele-MANAS को कॉल करो (मुफ़्त, 24x7)। इमरजेंसी में 112।',
  helpCall: 'Tele-MANAS 14416 पर कॉल करो',
  signOut: 'साइन आउट',
  loading: 'लोड हो रहा है…',
  back: 'वापस',
};

const ALL: Record<BuddyLanguage, Strings> = { 'en-IN': en, 'te-IN': te, 'ml-IN': ml, 'ta-IN': ta, 'hi-IN': hi };

export function strings(language: BuddyLanguage): Strings {
  return ALL[language] ?? en;
}

/** Topics to start from (in the learner's language; the buddy understands any). */
export const TOPIC_SUGGESTIONS: Record<BuddyLanguage, string[]> = {
  'te-IN': ['ప్రకాశసంశ్లేషణ', 'గురుత్వాకర్షణ', 'నీటి చక్రం', 'భిన్నాలు', 'సౌర వ్యవస్థ', 'Python basics'],
  'ml-IN': ['പ്രകാശസംശ്ലേഷണം', 'ഗുരുത്വാകർഷണം', 'ജലചക്രം', 'ഭിന്നസംഖ്യകൾ', 'സൗരയൂഥം', 'Python basics'],
  'ta-IN': ['ஒளிச்சேர்க்கை', 'புவியீர்ப்பு விசை', 'நீர் சுழற்சி', 'பின்னங்கள்', 'சூரியக் குடும்பம்', 'Python basics'],
  'hi-IN': ['प्रकाश संश्लेषण', 'गुरुत्वाकर्षण', 'जल चक्र', 'भिन्न', 'सौर मंडल', 'Python basics'],
  'en-IN': ['Photosynthesis', 'Gravity', 'The water cycle', 'Fractions', 'The solar system', 'Python basics'],
};

export function partOfDay(d = new Date()): 'morning' | 'afternoon' | 'evening' {
  const h = d.getHours();
  return h < 12 ? 'morning' : h < 17 ? 'afternoon' : 'evening';
}
