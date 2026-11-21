/**
 * UI words in the learner's language. The buddy speaks the session language;
 * the screen follows it too.
 */
import type { BuddyLanguage } from '@/types';

export const LANGUAGES: { code: BuddyLanguage; label: string; short: string }[] = [
  { code: 'ml-IN', label: 'മലയാളം', short: 'മല' },
  { code: 'te-IN', label: 'తెలుగు', short: 'తెలు' },
  { code: 'en-IN', label: 'English', short: 'EN' },
];

type Labels = {
  appName: string;
  tagline: string;
  hi: (name: string) => string;
  start: string;
  startAgain: string;
  pickLanguage: string;
  finished: string;
  finishedBody: string;
  connecting: string;
  listening: string;
  thinking: string;
  speaking: string;
  waiting: string;
  topic: string;
  noTopic: string;
  covered: (n: number, total: number) => string;
  you: string;
  buddy: string;
  muted: string;
  mute: string;
  unmute: string;
  end: string;
  endTitle: string;
  endBody: string;
  keepGoing: string;
  ending: string;
  tapForSound: string;
};

const en: Labels = {
  appName: 'Study Buddy',
  tagline: 'Learn by talking, in your own language.',
  hi: (name) => `Hi ${name}!`,
  start: 'Start studying',
  startAgain: 'Study again',
  pickLanguage: 'Language',
  finished: 'Nice work today!',
  finishedBody: 'Come back any time to keep going.',
  connecting: 'Connecting…',
  listening: 'Listening',
  thinking: 'Thinking…',
  speaking: 'Speaking',
  waiting: 'Waking up your buddy…',
  topic: 'Topic',
  noTopic: 'Say a topic to start',
  covered: (n, total) => `${n} of ${total} ideas`,
  you: 'You',
  buddy: 'Buddy',
  muted: 'Mic is off',
  mute: 'Turn mic off',
  unmute: 'Turn mic on',
  end: 'End',
  endTitle: 'Finish for today?',
  endBody: 'Your buddy will say goodbye.',
  keepGoing: 'Keep studying',
  ending: 'Finishing…',
  tapForSound: 'Tap to turn on sound',
};

const te: Labels = {
  ...en,
  appName: 'స్టడీ బడ్డీ',
  tagline: 'మాట్లాడుతూ నేర్చుకో, నీ భాషలోనే.',
  hi: (name) => `హాయ్ ${name}!`,
  start: 'చదువు మొదలుపెట్టు',
  startAgain: 'మళ్ళీ చదువుదాం',
  pickLanguage: 'భాష',
  finished: 'ఈ రోజు బాగా చేశావు!',
  finishedBody: 'ఎప్పుడైనా తిరిగి రా.',
  connecting: 'కనెక్ట్ అవుతోంది…',
  listening: 'వింటున్నాను',
  thinking: 'ఆలోచిస్తున్నాను…',
  speaking: 'మాట్లాడుతున్నాను',
  waiting: 'నీ బడ్డీ వస్తోంది…',
  topic: 'టాపిక్',
  noTopic: 'ఏదైనా టాపిక్ చెప్పు',
  covered: (n, total) => `${total}లో ${n} ఐడియాలు`,
  you: 'నువ్వు',
  buddy: 'బడ్డీ',
  muted: 'మైక్ ఆఫ్‌లో ఉంది',
  end: 'ముగించు',
  endTitle: 'ఈ రోజుకి ముగిద్దామా?',
  endBody: 'నీ బడ్డీ బై చెప్తుంది.',
  keepGoing: 'ఇంకా చదువుదాం',
  ending: 'ముగిస్తోంది…',
  tapForSound: 'సౌండ్ కోసం ట్యాప్ చేయి',
};

const ml: Labels = {
  ...en,
  appName: 'പഠിപ്പ് കൂട്ടുകാരൻ',
  tagline: 'സംസാരിച്ച് പഠിക്കാം, നിന്റെ സ്വന്തം ഭാഷയിൽ.',
  hi: (name) => `ഹായ് ${name}!`,
  start: 'പഠിക്കാൻ തുടങ്ങാം',
  startAgain: 'വീണ്ടും പഠിക്കാം',
  pickLanguage: 'ഭാഷ',
  finished: 'ഇന്ന് നന്നായി ചെയ്തു!',
  finishedBody: 'എപ്പോ വേണമെങ്കിലും തിരിച്ചു വരാം.',
  connecting: 'കണക്റ്റ് ചെയ്യുന്നു…',
  listening: 'കേൾക്കുന്നു',
  thinking: 'ആലോചിക്കുന്നു…',
  speaking: 'സംസാരിക്കുന്നു',
  waiting: 'നിന്റെ കൂട്ടുകാരൻ വരുന്നു…',
  topic: 'വിഷയം',
  noTopic: 'ഒരു വിഷയം പറയൂ',
  covered: (n, total) => `${total}ൽ ${n} ആശയങ്ങൾ`,
  you: 'നീ',
  buddy: 'കൂട്ടുകാരൻ',
  muted: 'മൈക്ക് ഓഫാണ്',
  end: 'നിർത്താം',
  endTitle: 'ഇന്നത്തേക്ക് നിർത്തണോ?',
  endBody: 'നിന്റെ കൂട്ടുകാരൻ ബൈ പറയും.',
  keepGoing: 'ഇനിയും പഠിക്കാം',
  ending: 'നിർത്തുന്നു…',
  tapForSound: 'ശബ്ദത്തിനായി ടാപ്പ് ചെയ്യൂ',
};

const ALL: Record<BuddyLanguage, Labels> = { 'en-IN': en, 'te-IN': te, 'ml-IN': ml };

export function labels(language: BuddyLanguage): Labels {
  return ALL[language] ?? en;
}

const LANGUAGE_KEY = 'buddy-language';

export function savedLanguage(): BuddyLanguage {
  try {
    const v = localStorage.getItem(LANGUAGE_KEY);
    if (LANGUAGES.some((l) => l.code === v)) return v as BuddyLanguage;
  } catch {
    /* storage unavailable (private mode): use the default */
  }
  return 'ml-IN';
}

export function saveLanguage(code: BuddyLanguage): void {
  try {
    localStorage.setItem(LANGUAGE_KEY, code);
  } catch {
    /* ignore */
  }
}
