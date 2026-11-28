import { describe, expect, it } from 'vitest';
import { hasLatinTitle, homeTopics } from './researchTopic';

describe('homeTopics', () => {
  it('keeps Latin-script titles, accents and symbols included, and drops others', () => {
    const topics = [
      { text: 'Small language models (<4B)', label: null },
      { text: 'Réseaux de neurones', label: null },
      { text: '大模型、后训练、Coding Agent、SFT', label: null },
      { text: '机器人的视觉语言动作模型', label: 'Vision-language-action models for robots' },
    ];
    expect(homeTopics(topics).map(topic => topic.text)).toEqual([
      'Small language models (<4B)',
      'Réseaux de neurones',
      '机器人的视觉语言动作模型',
    ]);
    expect(hasLatinTitle({ text: 'Raman spectra', label: null })).toBe(true);
  });
});
