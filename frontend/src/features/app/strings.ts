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
};

const en: Strings = {
  greet: (part, name) => `Good ${part}${name ? `, ${name}` : ''}`,
  nav: { home: 'Home', history: 'History', progress: 'Progress', profile: 'Me' },
  streak: (n) => (n === 1 ? '1 day' : `${n} days`),
  streakLabel: 'Streak',
  weekLabel: 'This week',
  ideasLabel: 'Ideas',
  studyTitle: 'Study with me',
  studyBody: 'Pick a topic. I explain it simply, ask gentle questions and help you get it.',
  talkTitle: 'Just talk',
  talkBody: 'Stressed, bored or just want company? Talk about anything. I listen.',
  startNow: 'Start',
  quickTopics: 'Quick start',
  continueTitle: 'Pick up where you left off',
  continueCta: 'Continue',
  ideasOf: (n, total) => `${n} of ${total} ideas`,
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
  keyIdeas: 'Key ideas',
  status: { understood: 'Got it', partial: 'Almost', gap: 'Still working', unseen: 'Not yet' },
  progressTitle: 'Your learning journey',
  last14: 'Last 14 days',
  sessionsTotal: 'Sessions',
  topicsLearned: 'Topics',
  progressEmpty: 'Your topics will show up here after your first study session.',
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
  ideasLabel: 'ఐడియాలు',
  studyTitle: 'నాతో చదువు',
  studyBody: 'ఒక టాపిక్ ఎంచుకో. నేను సింపుల్ గా చెప్పి, చిన్న ప్రశ్నలతో అర్థమయ్యేలా చేస్తాను.',
  talkTitle: 'ఊరికే మాట్లాడదాం',
  talkBody: 'స్ట్రెస్ గా ఉందా, బోర్ కొడుతోందా? ఏదైనా మాట్లాడు. నేను వింటాను.',
  startNow: 'మొదలుపెట్టు',
  quickTopics: 'త్వరగా మొదలుపెట్టు',
  continueTitle: 'ఆపిన చోటు నుంచి కొనసాగిద్దాం',
  continueCta: 'కొనసాగించు',
  ideasOf: (n, total) => `${total}లో ${n} ఐడియాలు`,
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
  keyIdeas: 'ముఖ్యమైన ఐడియాలు',
  status: { understood: 'అర్థమైంది', partial: 'దాదాపు', gap: 'ఇంకా ప్రయత్నిస్తున్నాం', unseen: 'ఇంకా లేదు' },
  progressTitle: 'నీ నేర్చుకునే ప్రయాణం',
  last14: 'గత 14 రోజులు',
  sessionsTotal: 'సెషన్లు',
  topicsLearned: 'టాపిక్స్',
  progressEmpty: 'నీ మొదటి స్టడీ సెషన్ తర్వాత నీ టాపిక్స్ ఇక్కడ కనిపిస్తాయి.',
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
  ideasLabel: 'ആശയങ്ങൾ',
  studyTitle: 'എന്റെ കൂടെ പഠിക്കാം',
  studyBody: 'ഒരു വിഷയം തിരഞ്ഞെടുക്കൂ. ഞാൻ ലളിതമായി പറഞ്ഞു തന്ന്, ചെറിയ ചോദ്യങ്ങളിലൂടെ മനസ്സിലാക്കി തരാം.',
  talkTitle: 'വെറുതെ സംസാരിക്കാം',
  talkBody: 'ടെൻഷനാണോ, ബോറടിക്കുന്നോ? എന്തും പറയാം. ഞാൻ കേൾക്കാം.',
  startNow: 'തുടങ്ങാം',
  quickTopics: 'വേഗം തുടങ്ങാം',
  continueTitle: 'നിർത്തിയിടത്തു നിന്ന് തുടരാം',
  continueCta: 'തുടരാം',
  ideasOf: (n, total) => `${total}ൽ ${n} ആശയങ്ങൾ`,
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
  keyIdeas: 'പ്രധാന ആശയങ്ങൾ',
  status: { understood: 'മനസ്സിലായി', partial: 'ഏതാണ്ട്', gap: 'ഇനിയും ശ്രമിക്കാം', unseen: 'ഇതുവരെ ഇല്ല' },
  progressTitle: 'നിന്റെ പഠന യാത്ര',
  last14: 'കഴിഞ്ഞ 14 ദിവസം',
  sessionsTotal: 'സെഷനുകൾ',
  topicsLearned: 'വിഷയങ്ങൾ',
  progressEmpty: 'ആദ്യത്തെ പഠന സെഷനു ശേഷം നിന്റെ വിഷയങ്ങൾ ഇവിടെ കാണാം.',
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

const ALL: Record<BuddyLanguage, Strings> = { 'en-IN': en, 'te-IN': te, 'ml-IN': ml };

export function strings(language: BuddyLanguage): Strings {
  return ALL[language] ?? en;
}

/** Topics to start from (in the learner's language; the buddy understands any). */
export const TOPIC_SUGGESTIONS: Record<BuddyLanguage, string[]> = {
  'te-IN': ['ప్రకాశసంశ్లేషణ', 'గురుత్వాకర్షణ', 'నీటి చక్రం', 'భిన్నాలు', 'సౌర వ్యవస్థ', 'Python basics'],
  'ml-IN': ['പ്രകാശസംശ്ലേഷണം', 'ഗുരുത്വാകർഷണം', 'ജലചക്രം', 'ഭിന്നസംഖ്യകൾ', 'സൗരയൂഥം', 'Python basics'],
  'en-IN': ['Photosynthesis', 'Gravity', 'The water cycle', 'Fractions', 'The solar system', 'Python basics'],
};

export function partOfDay(d = new Date()): 'morning' | 'afternoon' | 'evening' {
  const h = d.getHours();
  return h < 12 ? 'morning' : h < 17 ? 'afternoon' : 'evening';
}
