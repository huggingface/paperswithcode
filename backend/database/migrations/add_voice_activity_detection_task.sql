-- Add Voice Activity Detection as a top-level Audio task; production chat users
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
    'Voice Activity Detection',
    'voice-activity-detection',
    'Voice activity detection (VAD) determines which frames or segments of an audio signal contain human speech and which contain silence, noise, or other sounds. It is a lightweight front end for [Automatic Speech Recognition](/tasks/automatic-speech-recognition), [Speaker Diarization](/tasks/speaker-diarization), speech coding, and voice assistants, so models must be robust to noise and fast enough for streaming on-device use. Variants include personal (target-speaker) VAD and overlapped speech detection. Systems are evaluated with frame-level AUROC, F1, and detection error rates on datasets such as AVA-Speech, AMI, DIHARD, and noisy LibriSpeech mixtures.',
    'voice activity detection, voice activity detector, speech activity detection, speech activity detector, personal voice activity detection, target speaker voice activity detection, speech/non-speech detection, overlapped speech detection',
    (SELECT id FROM areas WHERE name = 'Audio' LIMIT 1),
    NULL,
    0,
    NULL,
    '[MarbleNet: Deep 1D Time-Channel Separable Convolutional Neural Network for Voice Activity Detection](/paper/2010.13886)',
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
