-- Hero image credits for the 2026-11-23 taxonomy gap fill. The images were
-- imported with import_entity_image.py from figures of the credited papers and,
-- for Viola-Jones, from Wikimedia Commons.

UPDATE tasks SET image_credit = '[Spam Detection Using BERT](/paper/2206.02443)' WHERE slug = 'spam-detection';
UPDATE tasks SET image_credit = '[RouteFinder: Towards Foundation Models for Vehicle Routing Problems](/paper/2406.15007)' WHERE slug = 'vehicle-routing-problem';
UPDATE tasks SET image_credit = '[AirPhyNet: Harnessing Physics-Guided Neural Networks for Air Quality Prediction](/paper/2402.03784)' WHERE slug = 'air-pollution-forecasting';
UPDATE tasks SET image_credit = '[HumanPlus: Humanoid Shadowing and Imitation from Humans](/paper/2406.10454)' WHERE slug = 'humanoid-robotics';
UPDATE tasks SET image_credit = '[Deep Bilateral Learning for Real-Time Image Enhancement](/paper/1707.02880)' WHERE slug = 'image-enhancement';
UPDATE tasks SET image_credit = '[MuSiQue: Multihop Questions via Single-hop Question Composition](/paper/2108.00573)' WHERE slug = 'multi-hop-question-answering';

UPDATE methods SET image_credit = '[Masked Feature Prediction for Self-Supervised Visual Pre-Training](/paper/2112.09133)' WHERE slug = 'hog';
UPDATE methods SET image_credit = '[Haar feature examples](https://commons.wikimedia.org/wiki/File:Haar_feature_examples.png), Cosmia Nebula, CC BY-SA 4.0' WHERE slug = 'viola-jones';
UPDATE methods SET image_credit = '[Anchor3DLane: Learning to Regress 3D Anchors for Monocular 3D Lane Detection](/paper/2301.02371)' WHERE slug = 'inverse-perspective-mapping';
UPDATE methods SET image_credit = '[SWAD: Domain Generalization by Seeking Flat Minima](/paper/2102.08604)' WHERE slug = 'swad';
