-- Add Automatic Music Transcription as a top-level Audio task; production chat users
-- searched for it but the catalog had no matching task.

INSERT INTO tasks (
    name,
    slug,
    description,
    keywords,
    area_id,
    parent_id,
    level,
    image_url,
    image_credit,
    is_visible
)
VALUES (
    'Automatic Music Transcription',
    'automatic-music-transcription',
    'Automatic music transcription (AMT) converts audio recordings of music into a symbolic representation such as MIDI or a piano roll, estimating the pitch, onset, offset, and often velocity and instrument of every note. Tasks range from single-instrument piano transcription to multi-instrument (multitrack) transcription, drum transcription, and singing-voice transcription. Models build on spectrogram-based [Audio Understanding](/tasks/audio-understanding) with convolutional, recurrent, and sequence-to-sequence Transformer architectures, and are evaluated with note-level onset (and offset) F1 via mir_eval on MAESTRO, MAPS, Slakh2100, MusicNet, and GuitarSet.',
    'automatic music transcription, music transcription, piano transcription, multi-instrument music transcription, multi-instrument transcription, multitrack music transcription, drum transcription, singing transcription, note transcription, audio-to-MIDI, audio to MIDI, multi-pitch estimation',
    (SELECT id FROM areas WHERE name = 'Audio' LIMIT 1),
    NULL,
    0,
    NULL,
    '[MT3: Multi-Task Multitrack Music Transcription](/paper/2111.03017)',
    true
)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    parent_id = EXCLUDED.parent_id,
    level = EXCLUDED.level,
    image_url = EXCLUDED.image_url,
    image_credit = EXCLUDED.image_credit,
    is_visible = EXCLUDED.is_visible,
    updated_at = CURRENT_TIMESTAMP;
