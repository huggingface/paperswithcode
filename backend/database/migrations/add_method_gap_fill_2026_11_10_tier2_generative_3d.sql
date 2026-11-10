-- Method gap fill (2026-11-10 audit), tier 2: generative personalization, 3D
-- reconstruction and model merging. 13 methods.
-- Sourced: DreamBooth (2208.12242), Textual Inversion (2208.01618), IP-Adapter
-- (2308.06721), Latent Consistency Model (2310.04378), NeuS (2106.10689),
-- Instant-NGP (2201.05989, indexed for this migration), Task Arithmetic
-- (2212.04089), TIES-Merging (2306.01708) and DARE (2311.03099, its own row,
-- not an alias of TIES-Merging).
-- Unsourced (contested or pre-arXiv origins, source_paper_id NULL): signed
-- distance function (classic level-set concept; DeepSDF 1901.05103 popularized
-- neural SDFs), triplane (Convolutional Occupancy Networks used canonical
-- feature planes before EG3D 2112.07945 named the tri-plane), structure from
-- motion and multi-view stereo. Their paper links below are reviewed
-- title/abstract candidates.
-- Hero images are imported separately with import_entity_image.py.
--
-- Keywords avoid bare abbreviations that are case-sensitive substrings in the
-- keyword backfill: "LCM" (Large Concept Model, LCM-based), "SDF", "MVS",
-- "SfM", "TIES", "DARE" and "task vector" (in-context-learning task vectors).
-- "LCM" is an alias only, with judged abstract linking.

INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, image_credit, abstract_linking, aliases
)
VALUES (
    'dreambooth', 'DreamBooth', 'DreamBooth',
    'DreamBooth personalizes a pretrained text-to-image [diffusion](/methods/diffusion) model to a specific subject from only three to five photos. It fine-tunes the whole model on prompts that pair a rare identifier token with the subject''s class noun (for example "a [V] dog"), so the identifier becomes bound to that subject and can be placed in new scenes, poses, styles and lighting through ordinary text prompts. To stop the model from overfitting and forgetting what the class looks like in general (language drift), DreamBooth adds a class-specific prior-preservation loss on images that the frozen model generates for the plain class prompt. The paper used Imagen and released the DreamBooth dataset of 30 subjects, scored with DINO and [CLIP](/methods/clip) image similarity and CLIP text alignment. The technique is widely applied to [Stable Diffusion](/methods/stable-diffusion), often with [LoRA](/methods/lora) to cut the cost of fine-tuning. [Textual Inversion](/methods/textual-inversion) instead learns only a new word embedding, and [Custom Diffusion](/paper/2212.04488) fine-tunes only the cross-attention projections.',
    'DreamBooth',
    (SELECT id FROM areas WHERE name = 'Vision' LIMIT 1),
    2022,
    (SELECT id FROM papers WHERE arxiv_id = '2208.12242'
     ORDER BY is_latest_version DESC, id DESC LIMIT 1),
    NULL,
    'DreamBooth: Fine Tuning Text-to-Image Diffusion Models for Subject-Driven Generation',
    'https://github.com/huggingface/diffusers/blob/main/examples/dreambooth/train_dreambooth.py',
    NULL,
    NULL,
    'always',
    ARRAY[]::text[]
)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    full_name = EXCLUDED.full_name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    introduced_year = EXCLUDED.introduced_year,
    source_paper_id = EXCLUDED.source_paper_id,
    source_url = EXCLUDED.source_url,
    source_title = EXCLUDED.source_title,
    code_snippet_url = EXCLUDED.code_snippet_url,
    abstract_linking = EXCLUDED.abstract_linking,
    aliases = EXCLUDED.aliases,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, image_credit, abstract_linking, aliases
)
VALUES (
    'textual-inversion',
    'Textual Inversion',
    'Textual Inversion',
    'Textual Inversion personalizes a text-to-image model by learning a new "word" for a user-provided concept, such as an object or an artistic style, from three to five images. The generator and text encoder stay frozen: only the embedding vector of a new pseudo-word (S*) in the text encoder''s input embedding space is optimized with the usual denoising loss, so that prompts containing the pseudo-word reconstruct the concept. The learned token then composes with natural language in new prompts ("a painting of S* in the style of ..."). The paper demonstrated it on a latent diffusion model, the architecture behind [Stable Diffusion](/methods/stable-diffusion), and showed that a single embedding captures much of a concept''s identity, at the cost of less fidelity than full fine-tuning. Textual Inversion is the lightest personalization method; [DreamBooth](/methods/dreambooth) fine-tunes the model weights for higher fidelity, and later encoder-based methods predict such embeddings in a single forward pass. The term is also used for inverting images into the text-embedding space for editing and for dataset analysis.',
    'textual inversion',
    (SELECT id FROM areas WHERE name = 'Vision' LIMIT 1),
    2022,
    (SELECT id FROM papers WHERE arxiv_id = '2208.01618'
     ORDER BY is_latest_version DESC, id DESC LIMIT 1),
    NULL,
    'An Image is Worth One Word: Personalizing Text-to-Image Generation using Textual Inversion',
    'https://github.com/huggingface/diffusers/blob/main/examples/textual_inversion/textual_inversion.py',
    NULL,
    NULL,
    'always',
    ARRAY[]::text[]
)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    full_name = EXCLUDED.full_name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    introduced_year = EXCLUDED.introduced_year,
    source_paper_id = EXCLUDED.source_paper_id,
    source_url = EXCLUDED.source_url,
    source_title = EXCLUDED.source_title,
    code_snippet_url = EXCLUDED.code_snippet_url,
    abstract_linking = EXCLUDED.abstract_linking,
    aliases = EXCLUDED.aliases,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, image_credit, abstract_linking, aliases
)
VALUES (
    'ip-adapter', 'IP-Adapter',
    'IP-Adapter (Image Prompt Adapter)',
    'IP-Adapter (Image Prompt Adapter) lets a pretrained text-to-image [diffusion](/methods/diffusion) model take an image as a prompt, alongside or instead of text, without fine-tuning the base model. A frozen [CLIP](/methods/clip) image encoder embeds the reference image, a small projection network turns that embedding into a few image tokens, and a decoupled [cross-attention](/methods/cross-attention) mechanism adds a new cross-attention layer for the image tokens next to each existing text cross-attention layer in the [U-Net](/methods/u-net); the two attention outputs are summed. Only about 22M adapter parameters are trained, and the result matches or beats fully fine-tuned image-prompt models. Because the base model is untouched, one trained adapter transfers to custom models fine-tuned from the same base, works with structural controls such as [ControlNet](/methods/controlnet), and keeps text prompts usable for multimodal prompting. Variants such as IP-Adapter-Plus, IP-Adapter-FaceID and SDXL adapters made it a standard tool for style transfer and identity-preserving generation with [Stable Diffusion](/methods/stable-diffusion), and it inspired encoder-based personalization methods such as [InstantID](/paper/2401.07519).',
    'IP-Adapter, IP Adapter, image prompt adapter',
    (SELECT id FROM areas WHERE name = 'Vision' LIMIT 1),
    2023,
    (SELECT id FROM papers WHERE arxiv_id = '2308.06721'
     ORDER BY is_latest_version DESC, id DESC LIMIT 1),
    NULL,
    'IP-Adapter: Text Compatible Image Prompt Adapter for Text-to-Image Diffusion Models',
    'https://github.com/tencent-ailab/IP-Adapter/blob/main/ip_adapter/attention_processor.py',
    NULL,
    NULL,
    'always',
    ARRAY[]::text[]
)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    full_name = EXCLUDED.full_name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    introduced_year = EXCLUDED.introduced_year,
    source_paper_id = EXCLUDED.source_paper_id,
    source_url = EXCLUDED.source_url,
    source_title = EXCLUDED.source_title,
    code_snippet_url = EXCLUDED.code_snippet_url,
    abstract_linking = EXCLUDED.abstract_linking,
    aliases = EXCLUDED.aliases,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, image_credit, abstract_linking, aliases
)
VALUES (
    'latent-consistency-model',
    'Latent Consistency Model',
    'Latent Consistency Model (LCM)',
    'A Latent Consistency Model (LCM) is a few-step image generator distilled from a pretrained latent diffusion model such as [Stable Diffusion](/methods/stable-diffusion). It applies [consistency distillation](/methods/consistency-models) in the autoencoder''s latent space: the student learns to map any point on a probability-flow ODE trajectory directly to the trajectory''s origin, so high-resolution images come out in one to four sampling steps instead of the 20 to 50 a diffusion sampler needs. LCMs treat guided sampling as solving an augmented probability-flow ODE that folds [classifier-free guidance](/methods/classifier-free-guidance) into the distillation, and use a skipping-step schedule to speed up training; distilling a 768x768 model took about 32 A100 GPU hours. Latent Consistency Fine-tuning adapts an LCM to a custom dataset, and [LCM-LoRA](/paper/2311.05556) packs the distilled weights into a [LoRA](/methods/lora) module that accelerates fine-tuned Stable Diffusion models without retraining. LCMs made near-real-time text-to-image generation practical and are a common baseline for few-step diffusion distillation.',
    'latent consistency model, latent consistency models',
    (SELECT id FROM areas WHERE name = 'Vision' LIMIT 1),
    2023,
    (SELECT id FROM papers WHERE arxiv_id = '2310.04378'
     ORDER BY is_latest_version DESC, id DESC LIMIT 1),
    NULL,
    'Latent Consistency Models: Synthesizing High-Resolution Images with Few-Step Inference',
    'https://github.com/luosiallen/latent-consistency-model',
    NULL,
    NULL,
    'judge',
    ARRAY['LCM']
)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    full_name = EXCLUDED.full_name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    introduced_year = EXCLUDED.introduced_year,
    source_paper_id = EXCLUDED.source_paper_id,
    source_url = EXCLUDED.source_url,
    source_title = EXCLUDED.source_title,
    code_snippet_url = EXCLUDED.code_snippet_url,
    abstract_linking = EXCLUDED.abstract_linking,
    aliases = EXCLUDED.aliases,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, image_credit, abstract_linking, aliases
)
VALUES (
    'signed-distance-function',
    'Signed Distance Function',
    'Signed Distance Function (SDF)',
    'A signed distance function (SDF) represents a shape implicitly: for every point in space it gives the distance to the nearest surface, with a negative sign inside the shape and a positive sign outside, so the surface is the zero-level set and the gradient of the field gives surface normals. SDFs are a long-standing tool in level-set methods, computer graphics and volumetric fusion (for example KinectFusion''s truncated SDF), and a mesh can be extracted from them with marching cubes. [DeepSDF](/paper/1901.05103) popularized neural SDFs, in which an MLP conditioned on a latent code regresses the signed distance of a query point, giving a continuous, memory-efficient representation of whole shape classes; [Occupancy Networks](/methods/occupancy-networks) proposed a closely related occupancy formulation at the same time. Later work learns SDFs from images by rendering them: [NeuS](/methods/neus) and [VolSDF](/paper/2106.12052) convert the SDF into a density for [NeRF](/methods/nerf)-style volume rendering, and [Neuralangelo](/paper/2306.03092) scales this with [multiresolution hash encodings](/methods/instant-ngp). Neural SDFs are used for 3D reconstruction, shape generation, robotics and collision checking.',
    'signed distance function, signed distance functions, signed distance field, signed distance fields',
    (SELECT id FROM areas WHERE name = 'Vision' LIMIT 1),
    NULL,
    NULL,
    'https://doi.org/10.1007/b98879',
    'Level Set Methods and Dynamic Implicit Surfaces',
    'https://github.com/facebookresearch/DeepSDF',
    NULL,
    NULL,
    'always',
    ARRAY['Signed Distance Field', 'Neural SDF', 'Neural Signed Distance Function']
)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    full_name = EXCLUDED.full_name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    introduced_year = EXCLUDED.introduced_year,
    source_paper_id = EXCLUDED.source_paper_id,
    source_url = EXCLUDED.source_url,
    source_title = EXCLUDED.source_title,
    code_snippet_url = EXCLUDED.code_snippet_url,
    abstract_linking = EXCLUDED.abstract_linking,
    aliases = EXCLUDED.aliases,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, image_credit, abstract_linking, aliases
)
VALUES (
    'neus', 'NeuS', 'NeuS',
    'NeuS reconstructs high-quality surfaces from multi-view images by representing a scene as the zero-level set of a neural [signed distance function](/methods/signed-distance-function) and training it with [NeRF](/methods/nerf)-style volume rendering. Its key contribution is a weight function derived from the SDF through a logistic density with a learnable sharpness, which is unbiased (it peaks exactly at the surface) and occlusion-aware, unlike naively turning distance into density. This lets NeuS learn complex geometry and thin structures without object masks, whereas earlier surface rendering methods such as IDR needed masks and NeRF''s density field yields noisy surfaces. On DTU and BlendedMVS it produced more accurate meshes than both. NeuS and the concurrent [VolSDF](/paper/2106.12052) established neural implicit surface reconstruction; follow-ups include NeuS2 and [Neuralangelo](/paper/2306.03092), which speed up training with [multiresolution hash encodings](/methods/instant-ngp), and SDF-based variants of [Gaussian splatting](/methods/gaussian-splatting).',
    'NeuS',
    (SELECT id FROM areas WHERE name = 'Vision' LIMIT 1),
    2021,
    (SELECT id FROM papers WHERE arxiv_id = '2106.10689'
     ORDER BY is_latest_version DESC, id DESC LIMIT 1),
    NULL,
    'NeuS: Learning Neural Implicit Surfaces by Volume Rendering for Multi-view Reconstruction',
    'https://github.com/Totoro97/NeuS/blob/main/models/renderer.py',
    NULL,
    NULL,
    'always',
    ARRAY[]::text[]
)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    full_name = EXCLUDED.full_name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    introduced_year = EXCLUDED.introduced_year,
    source_paper_id = EXCLUDED.source_paper_id,
    source_url = EXCLUDED.source_url,
    source_title = EXCLUDED.source_title,
    code_snippet_url = EXCLUDED.code_snippet_url,
    abstract_linking = EXCLUDED.abstract_linking,
    aliases = EXCLUDED.aliases,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, image_credit, abstract_linking, aliases
)
VALUES (
    'instant-ngp', 'Instant-NGP',
    'Instant Neural Graphics Primitives (Instant-NGP)',
    'Instant Neural Graphics Primitives (Instant-NGP) introduced the multiresolution hash encoding, an input encoding that lets small neural networks fit signals such as radiance fields, signed distance functions and gigapixel images in seconds to minutes. Space is covered by grids at several resolutions; the trainable feature vectors at each grid''s vertices are stored in a fixed-size hash table per level, so fine levels need no dense grid. A query point''s features are trilinearly interpolated at every level, concatenated and passed to a tiny MLP, and hash collisions are resolved implicitly by gradient descent. With fully fused CUDA kernels (tiny-cuda-nn), Instant-NGP cut [NeRF](/methods/nerf) training from hours to seconds while matching its quality. The hash grid became a standard backbone for neural fields, used by Nerfacto, [Neuralangelo](/paper/2306.03092), NeuS2 and many text-to-3D pipelines, and it influenced explicit-feature representations such as the [triplane](/methods/triplane) and [Gaussian splatting](/methods/gaussian-splatting).',
    'Instant-NGP, Instant NGP, InstantNGP, instant neural graphics primitives, multiresolution hash encoding, multi-resolution hash encoding',
    (SELECT id FROM areas WHERE name = 'Vision' LIMIT 1),
    2022,
    (SELECT id FROM papers WHERE arxiv_id = '2201.05989'
     ORDER BY is_latest_version DESC, id DESC LIMIT 1),
    NULL,
    'Instant Neural Graphics Primitives with a Multiresolution Hash Encoding',
    'https://github.com/NVlabs/tiny-cuda-nn/blob/master/include/tiny-cuda-nn/encodings/grid.h',
    NULL,
    NULL,
    'always',
    ARRAY['Multiresolution Hash Encoding', 'InstantNGP']
)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    full_name = EXCLUDED.full_name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    introduced_year = EXCLUDED.introduced_year,
    source_paper_id = EXCLUDED.source_paper_id,
    source_url = EXCLUDED.source_url,
    source_title = EXCLUDED.source_title,
    code_snippet_url = EXCLUDED.code_snippet_url,
    abstract_linking = EXCLUDED.abstract_linking,
    aliases = EXCLUDED.aliases,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, image_credit, abstract_linking, aliases
)
VALUES (
    'triplane', 'Triplane',
    'Tri-plane Representation',
    'A tri-plane (triplane) representation stores a 3D scene or object as three axis-aligned 2D feature planes (xy, xz and yz). To query a 3D point, it is projected onto each plane, a feature vector is bilinearly sampled from each, the three features are aggregated (usually summed or concatenated), and a small MLP decodes them into density and color, a [signed distance](/methods/signed-distance-function) or occupancy. This hybrid explicit-implicit design is far cheaper than a dense voxel grid and far faster to query than a large coordinate MLP such as [NeRF](/methods/nerf), and the planes can be produced by standard 2D convolutional networks. [Convolutional Occupancy Networks](/paper/2003.04618) used features on canonical planes for reconstruction; [EG3D](/paper/2112.07945) named the tri-plane and made it standard for 3D-aware GANs by generating the planes with a [StyleGAN](/methods/stylegan)2 backbone. Tri-planes are now used in 3D diffusion ([triplane diffusion](/paper/2211.16677)), feed-forward single-image reconstruction such as [LRM](/paper/2311.04400), avatars and dynamic scenes, where K-planes and HexPlane extend the idea to space-time. Related representations include [multiresolution hash grids](/methods/instant-ngp) and [Gaussian splatting](/methods/gaussian-splatting).',
    'triplane, tri-plane, triplanes, tri-planes',
    (SELECT id FROM areas WHERE name = 'Vision' LIMIT 1),
    NULL,
    NULL,
    'https://nvlabs.github.io/eg3d/',
    'Efficient Geometry-aware 3D Generative Adversarial Networks (EG3D)',
    'https://github.com/NVlabs/eg3d/blob/main/eg3d/training/triplane.py',
    NULL,
    NULL,
    'always',
    ARRAY['Tri-plane', 'Triplane Representation']
)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    full_name = EXCLUDED.full_name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    introduced_year = EXCLUDED.introduced_year,
    source_paper_id = EXCLUDED.source_paper_id,
    source_url = EXCLUDED.source_url,
    source_title = EXCLUDED.source_title,
    code_snippet_url = EXCLUDED.code_snippet_url,
    abstract_linking = EXCLUDED.abstract_linking,
    aliases = EXCLUDED.aliases,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, image_credit, abstract_linking, aliases
)
VALUES (
    'structure-from-motion',
    'Structure from Motion',
    'Structure from Motion (SfM)',
    'Structure from Motion (SfM) recovers the camera poses, and often the intrinsics, of a set of overlapping images together with a sparse 3D point cloud of the scene. A classic pipeline detects and matches local features such as SIFT across images, verifies matches geometrically with [RANSAC](/methods/ransac), then reconstructs the scene either incrementally, registering one image at a time, or globally, solving for all rotations and translations at once, and refines everything with bundle adjustment. The problem has roots in photogrammetry and the two-view geometry of the 1980s; Photo Tourism (Snavely et al., 2006) scaled it to internet photo collections, and COLMAP (Schönberger and Frahm, 2016) became the standard open-source incremental system, with [GLOMAP](/paper/2407.20219) revisiting the global approach. SfM poses are the usual input for [multi-view stereo](/methods/multi-view-stereo), [NeRF](/methods/nerf) and [Gaussian splatting](/methods/gaussian-splatting). Learned methods replace parts or all of the pipeline, from learned matchers to [VGGSfM](/paper/2312.04563), [DUSt3R](/methods/dust3r), [MASt3R](/paper/2406.09756) and [VGGT](/methods/vggt). [SLAM](/methods/slam) solves the related sequential, real-time problem.',
    'structure from motion, structure-from-motion',
    (SELECT id FROM areas WHERE name = 'Vision' LIMIT 1),
    NULL,
    NULL,
    'https://openaccess.thecvf.com/content_cvpr_2016/html/Schonberger_Structure-From-Motion_Revisited_CVPR_2016_paper.html',
    'Structure-from-Motion Revisited',
    'https://github.com/colmap/colmap',
    NULL,
    NULL,
    'always',
    ARRAY['Structure-from-Motion']
)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    full_name = EXCLUDED.full_name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    introduced_year = EXCLUDED.introduced_year,
    source_paper_id = EXCLUDED.source_paper_id,
    source_url = EXCLUDED.source_url,
    source_title = EXCLUDED.source_title,
    code_snippet_url = EXCLUDED.code_snippet_url,
    abstract_linking = EXCLUDED.abstract_linking,
    aliases = EXCLUDED.aliases,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, image_credit, abstract_linking, aliases
)
VALUES (
    'multi-view-stereo',
    'Multi-View Stereo',
    'Multi-View Stereo (MVS)',
    'Multi-view stereo (MVS) reconstructs dense 3D geometry, such as per-view depth maps, point clouds or meshes, from many images of a scene whose camera poses are known, usually from [structure from motion](/methods/structure-from-motion). It searches for the surface that is photo-consistent across views, matching image patches along epipolar lines or over depth hypotheses, then fuses the results into a single model. Classic approaches include volumetric and space-carving methods, patch-based PMVS (Furukawa and Ponce, 2010) and the PatchMatch depth estimation in COLMAP (Schönberger et al., 2016). Learning-based MVS started with [MVSNet](/paper/1804.02505), which warps deep features into a plane-sweep cost volume and regularizes it with 3D convolutions; cascade designs such as [CasMVSNet](/paper/1912.06378) raised resolution and efficiency. Standard benchmarks are DTU, Tanks and Temples and ETH3D. Neural implicit surfaces such as [NeuS](/methods/neus), [NeRF](/methods/nerf), [Gaussian splatting](/methods/gaussian-splatting) and feed-forward models such as [DUSt3R](/methods/dust3r) increasingly overlap with MVS.',
    'multi-view stereo, multiview stereo, multi view stereo',
    (SELECT id FROM areas WHERE name = 'Vision' LIMIT 1),
    NULL,
    NULL,
    'https://doi.org/10.1561/0600000052',
    'Multi-View Stereo: A Tutorial',
    NULL,
    NULL,
    NULL,
    'always',
    ARRAY['Multiview Stereo']
)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    full_name = EXCLUDED.full_name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    introduced_year = EXCLUDED.introduced_year,
    source_paper_id = EXCLUDED.source_paper_id,
    source_url = EXCLUDED.source_url,
    source_title = EXCLUDED.source_title,
    code_snippet_url = EXCLUDED.code_snippet_url,
    abstract_linking = EXCLUDED.abstract_linking,
    aliases = EXCLUDED.aliases,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, image_credit, abstract_linking, aliases
)
VALUES (
    'task-arithmetic',
    'Task Arithmetic',
    'Task Arithmetic',
    'Task arithmetic edits a pretrained model by adding or subtracting task vectors, where a task vector is the element-wise difference between a model''s weights after [fine-tuning](/methods/fine-tuning) on a task and its pretrained weights. Adding several task vectors, scaled by a coefficient, to the pretrained weights yields one model that performs all those tasks; negating a task vector makes the model forget a task or behavior, for example reducing toxic generations with little loss elsewhere; and analogies of the form A is to B as C is to D can improve a task without any data for it. The paper demonstrated these operations on [CLIP](/methods/clip) image classifiers and T5 and GPT-2 language models. Task arithmetic became a basic building block of [model merging](/methods/model-merging): [TIES-Merging](/methods/ties-merging) and [DARE](/methods/dare) reduce interference between task vectors before adding them, and later work studies why weight disentanglement in tangent space makes such edits work.',
    'task arithmetic',
    (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
    2022,
    (SELECT id FROM papers WHERE arxiv_id = '2212.04089'
     ORDER BY is_latest_version DESC, id DESC LIMIT 1),
    NULL,
    'Editing Models with Task Arithmetic',
    'https://github.com/mlfoundations/task_vectors/blob/main/src/task_vectors.py',
    NULL,
    NULL,
    'always',
    ARRAY[]::text[]
)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    full_name = EXCLUDED.full_name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    introduced_year = EXCLUDED.introduced_year,
    source_paper_id = EXCLUDED.source_paper_id,
    source_url = EXCLUDED.source_url,
    source_title = EXCLUDED.source_title,
    code_snippet_url = EXCLUDED.code_snippet_url,
    abstract_linking = EXCLUDED.abstract_linking,
    aliases = EXCLUDED.aliases,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, image_credit, abstract_linking, aliases
)
VALUES (
    'ties-merging', 'TIES-Merging',
    'TIES-Merging (TrIm, Elect Sign and Merge)',
    'TIES-Merging (TrIm, Elect Sign and Merge) combines several models fine-tuned from the same base into one multitask model while reducing interference between them. Working on task vectors, as in [task arithmetic](/methods/task-arithmetic), it proceeds in three steps: trim each task vector by keeping only its largest-magnitude changes (typically the top 20%) and resetting the rest to zero; elect a sign for each parameter from the direction with the larger total magnitude across models; and merge by averaging only the values that agree with the elected sign. The authors showed that redundant small updates and sign conflicts between models are the main causes of performance loss when merging, and TIES-Merging outperformed plain averaging, task arithmetic and [Fisher merging](/paper/2111.09832) across vision and language models, fully fine-tuned or adapted with parameter-efficient methods. It is one of the standard [model merging](/methods/model-merging) methods in toolkits such as mergekit, often combined with [DARE](/methods/dare) sparsification (DARE-TIES) to merge open LLMs.',
    'TIES-Merging, TIES merging, TIES-merging',
    (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
    2023,
    (SELECT id FROM papers WHERE arxiv_id = '2306.01708'
     ORDER BY is_latest_version DESC, id DESC LIMIT 1),
    NULL,
    'TIES-Merging: Resolving Interference When Merging Models',
    'https://github.com/arcee-ai/mergekit/blob/main/mergekit/merge_methods/generalized_task_arithmetic.py',
    NULL,
    NULL,
    'always',
    ARRAY[]::text[]
)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    full_name = EXCLUDED.full_name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    introduced_year = EXCLUDED.introduced_year,
    source_paper_id = EXCLUDED.source_paper_id,
    source_url = EXCLUDED.source_url,
    source_title = EXCLUDED.source_title,
    code_snippet_url = EXCLUDED.code_snippet_url,
    abstract_linking = EXCLUDED.abstract_linking,
    aliases = EXCLUDED.aliases,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, image_credit, abstract_linking, aliases
)
VALUES (
    'dare', 'DARE',
    'Drop And REscale (DARE)',
    'DARE (Drop And REscale) sparsifies the delta parameters of a fine-tuned model, the difference between its weights and those of its base model, before [model merging](/methods/model-merging). It randomly drops each delta parameter with probability p and rescales the survivors by 1/(1-p), which keeps the expected output unchanged; the authors found that supervised fine-tuned language models keep their abilities even when 90% or more of the delta parameters are dropped. Because the sparsified deltas of different models overlap less, merging them with [task arithmetic](/methods/task-arithmetic) or [TIES-Merging](/methods/ties-merging) causes less interference, and the paper merged instruction-following, math and code models derived from the same base, such as WizardLM and WizardMath, into one model with the combined abilities. DARE needs no retraining or GPUs, and DARE-TIES and DARE-linear are widely used in mergekit to build merged open LLMs. Unlike [dropout](/methods/dropout), DARE is applied once to weight differences after training.',
    'drop and rescale',
    (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
    2023,
    (SELECT id FROM papers WHERE arxiv_id = '2311.03099'
     ORDER BY is_latest_version DESC, id DESC LIMIT 1),
    NULL,
    'Language Models are Super Mario: Absorbing Abilities from Homologous Models as a Free Lunch',
    'https://github.com/arcee-ai/mergekit/blob/main/mergekit/merge_methods/generalized_task_arithmetic.py',
    NULL,
    NULL,
    'judge',
    ARRAY[]::text[]
)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    full_name = EXCLUDED.full_name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    introduced_year = EXCLUDED.introduced_year,
    source_paper_id = EXCLUDED.source_paper_id,
    source_url = EXCLUDED.source_url,
    source_title = EXCLUDED.source_title,
    code_snippet_url = EXCLUDED.code_snippet_url,
    abstract_linking = EXCLUDED.abstract_linking,
    aliases = EXCLUDED.aliases,
    updated_at = CURRENT_TIMESTAMP;

-- Introduced banners for the methods with a source paper.
INSERT INTO paper_methods (paper_id, method_id)
SELECT source_paper_id, id FROM methods
WHERE slug IN ('dreambooth', 'textual-inversion', 'ip-adapter', 'latent-consistency-model', 'neus', 'instant-ngp', 'task-arithmetic', 'ties-merging', 'dare')
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;


-- Reviewed paper links (2026-11-10). Sourced methods: local Semantic Scholar
-- citers of the source paper (link_papers_by_source_citations.py --write) plus
-- catalog papers whose title or abstract names the method. Heavily cited
-- sources collect many citers that never use the method, so only citers whose
-- title or abstract names it are kept; the rest become exclusions so the hourly
-- reference backfill does not re-link them. Unsourced methods: bounded
-- title/abstract regex candidates, reviewed one by one. Positives use, extend,
-- analyze, survey or compare against the method.

-- dreambooth: 67 links, 276 exclusions.
CREATE TEMP TABLE dreambooth_curated ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'dreambooth'
  AND p.id IN (
        10140, 13928, 14071, 14189, 14363, 14515, 15239, 15691, 16005, 16124, 16808, 18060, 18134, 18220, 19846, 19965,
        20039, 20088, 20689, 20924, 22566, 22956, 24072, 24290, 25818, 26266, 28055, 28291, 28359, 30063, 31637, 32514,
        34252, 34451, 34505, 34788, 37382, 37984, 38231, 38652, 41083, 41253, 45709, 46527, 47350, 47985, 49729, 51738,
        56857, 65398, 66679, 72662, 85261, 87201, 89449, 90504, 107175, 112538, 112911, 115619, 116117, 116155, 116206, 116818,
        120370, 122935, 131626
  );

DELETE FROM paper_method_exclusions x
USING dreambooth_curated c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM dreambooth_curated
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM dreambooth_curated
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

CREATE TEMP TABLE dreambooth_excluded ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'dreambooth'
  AND p.id IN (
        53862, 53865, 53882, 53899, 53958, 54008, 54165, 54243, 54272, 54403, 54448, 54460, 54463, 54480, 54513, 54524,
        54556, 54587, 54594, 54643, 54658, 54686, 54722, 54727, 54773, 54781, 54795, 54870, 54943, 55034, 55036, 55078,
        55108, 55121, 55171, 55323, 55336, 55652, 55680, 55741, 55774, 55998, 56053, 56206, 56225, 56436, 56488, 56567,
        56606, 56625, 56653, 56692, 56734, 56763, 56898, 56954, 56980, 57028, 57074, 57128, 57134, 57135, 57200, 57205,
        57242, 57335, 57341, 57366, 57371, 57633, 57793, 57813, 57827, 58215, 58360, 58507, 58764, 58767, 58796, 58874,
        58995, 59059, 59097, 59160, 59285, 59457, 59766, 60000, 60057, 60191, 60265, 60309, 60344, 60390, 60704, 60984,
        61357, 61531, 61779, 62372, 62596, 62672, 62698, 62770, 62942, 63000, 63109, 63150, 63214, 63219, 63430, 63757,
        63764, 63772, 63783, 63938, 63987, 64154, 64156, 64256, 64308, 64481, 64498, 64562, 64680, 64688, 64705, 64766,
        64830, 64833, 64938, 65299, 65541, 65760, 65766, 65791, 65907, 82847, 83005, 83317, 83767, 83769, 83818, 83822,
        83917, 84162, 84259, 84275, 84296, 84340, 84357, 84381, 84402, 84405, 84418, 84422, 84485, 84494, 84534, 84557,
        84563, 84611, 84618, 84778, 84831, 84865, 84881, 84907, 84932, 84951, 84964, 85003, 85011, 85044, 85056, 85093,
        85112, 85188, 85223, 85283, 85285, 85305, 85340, 85393, 85408, 85532, 93374, 93463, 94571, 98317, 98482, 98540,
        98586, 98754, 98755, 98846, 98884, 99033, 99115, 99264, 99533, 99736, 99763, 99962, 100430, 100526, 100823, 100863,
        101368, 102185, 102414, 102461, 103447, 103906, 103947, 104000, 104015, 104395, 104829, 105980, 106067, 106789, 106793, 106981,
        107225, 107510, 107534, 107584, 107742, 107919, 108253, 108289, 108318, 109065, 109396, 113986, 114015, 117454, 117562, 118136,
        118363, 118422, 118440, 118506, 118550, 118551, 118578, 118590, 118623, 118632, 118676, 118864, 118936, 119192, 119558, 120758,
        121184, 121276, 122264, 122582, 122853, 122904, 122948, 123408, 124162, 124796, 124963, 127570, 130238, 130997, 131065, 131556,
        131659, 131696, 131944, 131994
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'Method gap fill 2026-11-10: cites DreamBooth without naming it in the title or abstract'
FROM dreambooth_excluded
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING dreambooth_excluded x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING dreambooth_excluded x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- textual-inversion: 68 links, 1375 exclusions.
CREATE TEMP TABLE textual_inversion_curated ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'textual-inversion'
  AND p.id IN (
        9962, 11719, 12939, 13125, 13835, 14177, 14363, 14515, 15691, 15955, 16005, 16592, 16808, 17698, 17924, 18220,
        18566, 20007, 20039, 20443, 21877, 23780, 24072, 24290, 24435, 24786, 25203, 25818, 26378, 27325, 27743, 28318,
        29302, 31071, 32514, 34252, 34820, 34868, 35429, 35687, 36250, 38614, 40153, 40969, 46365, 47919, 49677, 54781,
        58730, 58995, 63000, 74197, 87201, 87575, 88035, 88356, 112538, 112911, 113503, 115352, 116117, 116540, 117562, 118399,
        118687, 120287, 120631, 121857
  );

DELETE FROM paper_method_exclusions x
USING textual_inversion_curated c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM textual_inversion_curated
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM textual_inversion_curated
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

CREATE TEMP TABLE textual_inversion_excluded ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'textual-inversion'
  AND p.id IN (
        7607, 8531, 8591, 10140, 10409, 10866, 10871, 11115, 11188, 11341, 11348, 11417, 11418, 11457, 11504, 11529,
        11540, 11546, 11576, 11580, 11621, 11698, 11701, 11707, 11728, 11734, 11837, 11874, 11875, 12180, 12189, 12248,
        12259, 12278, 12433, 12485, 12650, 12722, 12819, 12892, 12926, 12976, 13021, 13023, 13082, 13129, 13203, 13228,
        13229, 13234, 13281, 13283, 13314, 13320, 13336, 13467, 13578, 13595, 13599, 13719, 13749, 13751, 13752, 13759,
        13869, 13873, 13894, 13914, 13928, 13929, 13933, 14011, 14044, 14067, 14071, 14074, 14078, 14189, 14190, 14202,
        14289, 14392, 14442, 14443, 14603, 14684, 14760, 14831, 15153, 15239, 15257, 15316, 15569, 15579, 15672, 15708,
        15722, 15872, 15905, 15910, 15939, 15963, 16002, 16124, 16232, 16246, 16258, 16275, 16311, 16320, 16363, 16410,
        16485, 16490, 16493, 16494, 16498, 16500, 16522, 16551, 16561, 16621, 16720, 16790, 16795, 16799, 16801, 16810,
        16893, 16922, 16985, 17120, 17125, 17160, 17173, 17271, 17318, 17378, 17404, 17448, 17497, 17537, 17560, 17674,
        17711, 17749, 17877, 17883, 17897, 17898, 17938, 18006, 18045, 18060, 18134, 18140, 18214, 18216, 18218, 18291,
        18382, 18397, 18400, 18416, 18453, 18464, 18487, 18503, 18561, 18667, 18672, 18676, 18684, 18725, 18846, 18879,
        18921, 18947, 19000, 19044, 19200, 19334, 19422, 19483, 19831, 19839, 19841, 19980, 20088, 20162, 20175, 20184,
        20292, 20296, 20305, 20319, 20363, 20366, 20596, 20689, 20690, 20740, 20899, 20908, 20969, 20972, 20978, 20984,
        20988, 21046, 21090, 21115, 21217, 21264, 21271, 21283, 21304, 21356, 21398, 21473, 21621, 21702, 21726, 21749,
        21768, 21792, 21850, 21855, 21967, 22034, 22066, 22159, 22187, 22309, 22314, 22490, 22526, 22613, 22671, 22714,
        22771, 22836, 22864, 22886, 22910, 22956, 22984, 23129, 23175, 23207, 23262, 23391, 23396, 23398, 23418, 23465,
        23468, 23473, 23496, 23519, 23546, 23577, 23624, 23677, 23714, 23726, 23752, 23793, 23794, 23809, 23849, 23850,
        23869, 23873, 23877, 23892, 23915, 23930, 23949, 23969, 24038, 24061, 24099, 24106, 24133, 24139, 24147, 24155,
        24197, 24224, 24225, 24230, 24233, 24249, 24255, 24271, 24282, 24292, 24300, 24305, 24314, 24321, 24327, 24329,
        24332, 24335, 24357, 24358, 24359, 24360, 24388, 24389, 24398, 24430, 24437, 24448, 24463, 24474, 24486, 24490,
        24499, 24521, 24563, 24572, 24590, 24601, 24696, 24725, 24771, 24800, 24811, 24816, 24837, 24857, 24894, 24905,
        24907, 24954, 24964, 24973, 24997, 25015, 25052, 25054, 25073, 25075, 25097, 25111, 25140, 25167, 25190, 25211,
        25222, 25227, 25232, 25277, 25281, 25284, 25292, 25500, 25601, 25757, 25946, 25974, 25987, 26069, 26139, 26229,
        26253, 26266, 26276, 26305, 26338, 26381, 26383, 26405, 26419, 26467, 26473, 26482, 26526, 26549, 26576, 26826,
        26836, 26860, 26864, 26999, 27021, 27027, 27104, 27262, 27268, 27282, 27351, 27363, 27366, 27386, 27551, 27663,
        27832, 27907, 28025, 28055, 28067, 28176, 28241, 28291, 28326, 28342, 28508, 28546, 28556, 28563, 28567, 28570,
        28588, 28644, 28666, 28682, 28718, 28738, 28748, 28873, 28910, 28953, 28967, 28974, 28978, 29018, 29023, 29024,
        29035, 29105, 29109, 29130, 29141, 29191, 29195, 29235, 29244, 29271, 29274, 29276, 29300, 29308, 29315, 29334,
        29339, 29402, 29445, 29448, 29450, 29526, 29546, 29549, 29554, 29595, 29638, 29666, 29669, 29745, 29746, 29767,
        29788, 29800, 29854, 29887, 29955, 29972, 29984, 30000, 30063, 30065, 30081, 30092, 30096, 30149, 30159, 30191,
        30216, 30224, 30253, 30255, 30350, 30384, 30406, 30475, 30495, 30530, 30617, 30633, 30646, 30671, 30711, 30713,
        30729, 30746, 30771, 30785, 30823, 30831, 30868, 30902, 30925, 30961, 31012, 31023, 31079, 31169, 31179, 31214,
        31219, 31476, 31481, 31483, 31539, 31566, 31606, 31650, 31671, 31757, 31777, 31811, 31845, 31855, 31859, 31881,
        31896, 31948, 32059, 32080, 32108, 32142, 32164, 32194, 32335, 32367, 32483, 32526, 32578, 32603, 32612, 32631,
        32691, 32734, 32738, 32813, 32841, 32864, 32875, 32880, 32895, 32903, 32927, 33229, 33351, 33377, 33425, 33486,
        33488, 33580, 33611, 33630, 33649, 33683, 33772, 33778, 33862, 33965, 34058, 34209, 34272, 34274, 34330, 34352,
        34367, 34390, 34397, 34400, 34505, 34590, 34674, 34729, 34788, 34930, 34952, 35042, 35155, 35174, 35304, 35321,
        35396, 35448, 35532, 35611, 35699, 35719, 35741, 35788, 35831, 35957, 35959, 36086, 36180, 36200, 36261, 36267,
        36360, 36526, 36546, 36629, 36661, 36670, 36697, 36815, 36833, 36894, 36901, 36999, 37020, 37077, 37120, 37180,
        37210, 37321, 37325, 37370, 37382, 37391, 37489, 37521, 37585, 37590, 37636, 37681, 37693, 37716, 37791, 37983,
        37984, 37985, 38015, 38040, 38053, 38110, 38177, 38231, 38235, 38272, 38353, 38387, 38403, 38411, 38415, 38514,
        38560, 38594, 38701, 38702, 38718, 38750, 38803, 38847, 38851, 38889, 38984, 38985, 39036, 39127, 39133, 39149,
        39379, 39407, 39458, 39498, 39693, 39762, 39877, 39889, 39892, 40004, 40179, 40230, 40278, 40319, 40338, 40340,
        40343, 40360, 40446, 40479, 40484, 40497, 40513, 40551, 40588, 40613, 40622, 40675, 40740, 40746, 40817, 40820,
        40834, 40884, 40940, 40962, 40974, 41006, 41019, 41042, 41083, 41136, 41139, 41155, 41253, 41308, 41324, 41326,
        41342, 41386, 41407, 41431, 41441, 41486, 41492, 41498, 41514, 41595, 41616, 41656, 41661, 41709, 41810, 41853,
        41875, 41933, 42000, 42100, 42203, 42254, 42424, 42426, 42452, 42582, 42596, 42633, 42634, 42635, 42668, 42693,
        42721, 42739, 42760, 42802, 42849, 42850, 42852, 42870, 42913, 42932, 43059, 43063, 43089, 43162, 43195, 43257,
        43278, 43602, 43655, 43659, 43744, 43756, 43794, 43841, 43934, 43949, 44003, 44142, 44150, 44225, 44273, 44511,
        44644, 44698, 44742, 44947, 45027, 45030, 45112, 45156, 45160, 45247, 45418, 45495, 45601, 45698, 45709, 45741,
        45750, 45758, 45788, 45814, 45879, 45937, 45944, 45956, 45994, 46013, 46018, 46038, 46042, 46047, 46066, 46083,
        46174, 46186, 46208, 46213, 46267, 46322, 46363, 46446, 46488, 46528, 46532, 46535, 46855, 46885, 47012, 47077,
        47081, 47202, 47203, 47207, 47224, 47239, 47283, 47430, 47455, 47482, 47536, 47752, 47791, 47811, 47839, 47870,
        47927, 47929, 48047, 48089, 48104, 48111, 48123, 48193, 48244, 48328, 48415, 48433, 48459, 48489, 48613, 48644,
        48716, 48784, 48847, 49066, 49562, 49671, 49729, 49847, 49861, 49912, 50000, 50099, 50154, 50365, 50463, 50529,
        50838, 50953, 51014, 51379, 51411, 51503, 51513, 51704, 51753, 51761, 51839, 51902, 51908, 51921, 51975, 52065,
        52086, 52249, 52308, 52321, 52424, 52479, 52529, 52540, 52691, 52804, 52879, 52958, 52969, 53046, 53237, 53372,
        53387, 53390, 53449, 53497, 53618, 53649, 53794, 53862, 53865, 53882, 53961, 54008, 54243, 54403, 54448, 54463,
        54480, 54524, 54594, 54643, 54686, 54722, 54870, 54943, 55034, 55036, 55108, 55121, 55171, 55323, 55652, 55680,
        56225, 56556, 56567, 56606, 56625, 56763, 56857, 56898, 56954, 57134, 57242, 57335, 57366, 57371, 57793, 58159,
        58215, 58360, 58739, 58764, 59052, 59094, 59097, 59457, 59608, 60057, 60243, 60265, 60309, 60370, 60390, 60984,
        61357, 61531, 61583, 61779, 61923, 62672, 62698, 62770, 62942, 63219, 63234, 63757, 63772, 63783, 63938, 64156,
        64256, 64308, 64371, 64481, 64520, 64562, 64580, 64636, 64688, 64705, 64766, 65398, 65541, 65602, 65658, 65766,
        65791, 65823, 65952, 66118, 66133, 66363, 66679, 66820, 66846, 66891, 66956, 67170, 67279, 67315, 67322, 67357,
        67573, 67646, 67927, 68045, 68194, 68890, 68901, 68986, 69119, 69430, 69431, 69538, 69615, 69619, 69793, 69803,
        69809, 69834, 69847, 69889, 70003, 70199, 70208, 70400, 70438, 70486, 70533, 70680, 70802, 70820, 70825, 70942,
        70956, 71188, 71193, 71280, 71393, 71422, 71503, 71511, 71784, 71786, 71919, 71943, 72073, 72119, 72320, 72323,
        72341, 72609, 72662, 72686, 72789, 72798, 72919, 73087, 73112, 73150, 73237, 73244, 73264, 73444, 73459, 73555,
        73882, 73922, 74004, 74075, 74107, 74175, 74623, 75491, 75605, 75729, 75748, 75767, 75928, 76224, 76462, 76571,
        76665, 76948, 77451, 77525, 78063, 78160, 78174, 78324, 78633, 78660, 78803, 79014, 79098, 79368, 82847, 83317,
        83767, 83769, 83818, 83917, 83996, 84052, 84081, 84340, 84381, 84402, 84485, 84494, 84534, 84611, 84682, 84814,
        84831, 84865, 84932, 84964, 85003, 85011, 85023, 85093, 85100, 85223, 85283, 85285, 85305, 85340, 85408, 85592,
        85724, 85778, 86559, 86649, 86665, 86679, 86882, 87243, 87343, 87542, 87549, 87560, 87592, 87721, 87731, 87737,
        87750, 87885, 87894, 87904, 87913, 88037, 88196, 88237, 88257, 88273, 88348, 88455, 88459, 88498, 89065, 89293,
        89440, 89449, 89501, 89756, 90091, 90150, 90162, 90191, 90216, 90264, 90277, 90282, 90336, 90406, 90427, 90441,
        90504, 90565, 90671, 90727, 90752, 90844, 90878, 90893, 90954, 90961, 91142, 91157, 91700, 91811, 91945, 91974,
        92010, 92054, 92268, 92369, 93411, 93497, 93780, 93925, 93959, 94157, 94351, 94391, 94502, 94756, 94986, 95035,
        98540, 98586, 98846, 99264, 99533, 99763, 99972, 100533, 100863, 101368, 101895, 103447, 103906, 103947, 104000, 104771,
        104829, 105391, 105980, 106793, 107019, 107061, 107225, 107227, 107607, 107850, 107919, 108302, 108318, 109065, 109396, 109410,
        109897, 109921, 110317, 110570, 111354, 111683, 112223, 112258, 112298, 112357, 112500, 112514, 112557, 112632, 112720, 112759,
        112763, 112780, 112850, 112973, 112981, 113011, 113092, 113290, 113427, 113445, 113481, 113516, 113520, 113558, 113568, 113592,
        113635, 113657, 115589, 115594, 115619, 115642, 115657, 115703, 115744, 115766, 115835, 115842, 115979, 116018, 116098, 116110,
        116143, 116144, 116155, 116222, 116229, 116277, 116292, 116338, 116472, 116604, 116646, 116663, 116726, 116818, 116835, 116901,
        116907, 116926, 117016, 117027, 117165, 117186, 117206, 117234, 117243, 117326, 117454, 118363, 118395, 118422, 118440, 118544,
        118550, 118676, 118864, 118936, 118986, 119558, 119880, 120047, 120197, 120216, 120238, 120488, 120501, 120544, 120628, 120758,
        121184, 121276, 122935, 123408, 124058, 124162, 125233, 127570, 127703, 129567, 130238, 130646, 130991, 130997, 131556
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'Method gap fill 2026-11-10: cites Textual Inversion without naming it in the title or abstract'
FROM textual_inversion_excluded
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING textual_inversion_excluded x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING textual_inversion_excluded x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- ip-adapter: 40 links, 971 exclusions.
CREATE TEMP TABLE ip_adapter_curated ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'ip-adapter'
  AND p.id IN (
        19200, 24335, 27076, 28291, 28359, 30350, 32228, 34833, 35594, 35708, 36546, 36625, 38652, 39149, 40563, 40575,
        40822, 41488, 42296, 42400, 44604, 45112, 45709, 45750, 46042, 46527, 49729, 52804, 53150, 53449, 54165, 69046,
        69615, 76850, 90233, 90504, 118393, 118459, 121428, 121777
  );

DELETE FROM paper_method_exclusions x
USING ip_adapter_curated c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM ip_adapter_curated
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM ip_adapter_curated
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

CREATE TEMP TABLE ip_adapter_excluded ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'ip-adapter'
  AND p.id IN (
        15672, 16561, 16780, 16803, 18134, 18382, 20088, 21536, 21609, 21809, 22185, 22753, 22956, 23465, 23859, 23892,
        23923, 23949, 23969, 23986, 24022, 24036, 24139, 24224, 24225, 24230, 24239, 24247, 24255, 24271, 24290, 24305,
        24314, 24352, 24399, 24430, 24433, 24435, 24437, 24486, 24503, 24638, 24775, 24800, 24813, 24907, 25052, 25086,
        25089, 25232, 25405, 25417, 25443, 25718, 25818, 25945, 26059, 26179, 26266, 26276, 26405, 26552, 26576, 27021,
        27325, 27384, 27658, 27663, 27751, 28025, 28037, 28055, 28067, 28118, 28342, 28344, 28417, 28564, 28569, 28570,
        28682, 28738, 28825, 28832, 28873, 28953, 28974, 28978, 28988, 29024, 29035, 29069, 29113, 29141, 29191, 29271,
        29274, 29276, 29299, 29300, 29302, 29315, 29444, 29448, 29454, 29535, 29546, 29554, 29627, 29666, 29824, 29853,
        29887, 29955, 30036, 30037, 30081, 30092, 30145, 30146, 30149, 30216, 30253, 30389, 30406, 30530, 30622, 30646,
        30711, 30713, 30717, 30729, 30746, 30785, 30925, 31012, 31023, 31169, 31214, 31231, 31256, 31481, 31530, 31566,
        31606, 31619, 31631, 31774, 31777, 31845, 31921, 32098, 32117, 32234, 32272, 32285, 32307, 32442, 32514, 32631,
        32691, 32734, 32738, 32827, 32864, 32888, 32903, 33129, 33377, 33580, 33611, 33765, 33778, 33917, 33965, 33975,
        33994, 34058, 34274, 34446, 34451, 34505, 34536, 34727, 34788, 34841, 35042, 35078, 35114, 35308, 35567, 35687,
        35699, 35741, 35818, 35831, 35959, 36035, 36111, 36135, 36141, 36266, 36378, 36391, 36483, 36486, 36506, 36593,
        36697, 36804, 36814, 36901, 36999, 37077, 37120, 37228, 37321, 37325, 37370, 37382, 37391, 37455, 37484, 37489,
        37521, 37563, 37632, 37681, 37713, 37716, 37924, 37983, 37985, 38040, 38110, 38131, 38177, 38184, 38185, 38231,
        38267, 38268, 38387, 38392, 38515, 38530, 38594, 38612, 38621, 38701, 38744, 38750, 38797, 38851, 38909, 39122,
        39179, 39293, 39370, 39379, 39388, 39407, 39433, 39608, 39693, 39716, 39755, 39762, 39851, 39853, 40056, 40179,
        40195, 40230, 40293, 40319, 40338, 40339, 40343, 40354, 40360, 40384, 40422, 40446, 40462, 40481, 40484, 40497,
        40504, 40511, 40513, 40543, 40551, 40588, 40590, 40593, 40613, 40622, 40662, 40666, 40675, 40690, 40740, 40793,
        40813, 40820, 40834, 40881, 40940, 40944, 40957, 40962, 40974, 40989, 41006, 41019, 41023, 41042, 41051, 41136,
        41139, 41308, 41313, 41324, 41326, 41328, 41341, 41386, 41441, 41451, 41492, 41498, 41595, 41661, 41709, 41714,
        41789, 41849, 41858, 41993, 42059, 42100, 42184, 42201, 42203, 42254, 42292, 42381, 42426, 42452, 42477, 42480,
        42564, 42582, 42633, 42652, 42668, 42693, 42721, 42753, 42779, 42834, 42849, 42857, 42907, 42913, 42932, 42955,
        43021, 43028, 43059, 43060, 43162, 43257, 43289, 43591, 43602, 43655, 43934, 44054, 44062, 44150, 44193, 44225,
        44273, 44511, 44626, 44914, 44947, 45016, 45023, 45027, 45136, 45156, 45159, 45160, 45201, 45276, 45289, 45663,
        45676, 45689, 45698, 45725, 45758, 45776, 45779, 45780, 45824, 45860, 45875, 45879, 45900, 45937, 45941, 45944,
        46004, 46018, 46031, 46032, 46038, 46044, 46047, 46061, 46066, 46083, 46153, 46174, 46204, 46208, 46213, 46230,
        46267, 46313, 46322, 46342, 46351, 46353, 46423, 46446, 46488, 46507, 46572, 46661, 46679, 46707, 46738, 46739,
        46769, 46785, 46855, 46876, 46914, 46915, 47077, 47081, 47203, 47224, 47246, 47293, 47322, 47351, 47440, 47443,
        47481, 47482, 47523, 47707, 47739, 47752, 47809, 47810, 47811, 47856, 47870, 47875, 47919, 47927, 47945, 47985,
        48012, 48018, 48047, 48061, 48089, 48111, 48123, 48193, 48244, 48273, 48403, 48415, 48433, 48479, 48644, 48651,
        48836, 48948, 48962, 49562, 49610, 49680, 49687, 49692, 49849, 49861, 49912, 49919, 49926, 50099, 50108, 50148,
        50154, 50353, 50440, 50463, 50492, 50529, 50648, 50788, 50814, 50953, 50966, 51379, 51388, 51426, 51513, 51613,
        51642, 51728, 51742, 51839, 51908, 52065, 52156, 52249, 52273, 52292, 52308, 52311, 52321, 52355, 52377, 52384,
        52424, 52479, 52529, 52562, 52594, 52657, 52691, 52796, 52879, 52969, 52985, 53046, 53062, 53064, 53387, 53534,
        53594, 53644, 53649, 53683, 53794, 53862, 54008, 54243, 54286, 54301, 54354, 54403, 54412, 54417, 54448, 54463,
        54480, 54497, 54601, 54643, 54685, 54722, 54770, 54781, 54795, 54893, 55034, 55036, 55116, 55121, 55171, 55323,
        55387, 55652, 55747, 55774, 56556, 56567, 56625, 56763, 56766, 56796, 56857, 56980, 57135, 57202, 57215, 57242,
        57599, 57793, 57813, 57827, 57832, 58306, 58335, 58360, 58642, 58796, 58814, 58825, 59074, 59094, 59190, 59505,
        59807, 59825, 59837, 60087, 60143, 60237, 60309, 60344, 60390, 60394, 60455, 60662, 60765, 60793, 61043, 61078,
        61313, 61357, 61531, 61727, 61779, 61887, 62596, 62672, 62770, 62799, 63219, 63234, 63538, 63722, 63724, 63753,
        63757, 63785, 63859, 63898, 63925, 63987, 64156, 64256, 64308, 64414, 64562, 64593, 64607, 64636, 64705, 64721,
        64766, 64830, 65299, 65353, 65463, 65541, 65791, 65818, 65823, 65837, 65848, 65952, 66093, 66317, 66820, 66846,
        66891, 66940, 67088, 67170, 67279, 67315, 67357, 67395, 67471, 67722, 68045, 68085, 68285, 68726, 68752, 68890,
        68894, 68960, 69041, 69431, 69516, 69532, 69709, 69758, 69803, 70010, 70105, 70214, 70293, 70294, 70400, 70486,
        70532, 70753, 70942, 70953, 71015, 71183, 71245, 71393, 71408, 71503, 71598, 71635, 71712, 71720, 71843, 71917,
        71919, 71994, 72073, 72181, 72213, 72286, 72341, 72360, 72369, 72919, 73119, 73163, 73242, 73604, 73610, 73761,
        73894, 74045, 74302, 74310, 74349, 74419, 74426, 74738, 74955, 75083, 75491, 75599, 75605, 75644, 75729, 76462,
        76571, 76833, 77117, 77651, 77857, 82847, 82954, 83237, 83317, 83449, 83767, 83769, 83818, 83917, 84052, 84205,
        84275, 84280, 84323, 84370, 84378, 84381, 84402, 84422, 84473, 84494, 84529, 84618, 84782, 84907, 84977, 85025,
        85223, 85283, 85342, 85363, 85408, 85499, 85559, 86020, 86300, 86559, 86774, 87113, 87243, 87452, 87549, 87684,
        87742, 87813, 87845, 87863, 87885, 87890, 87894, 87977, 88027, 88144, 88159, 88208, 88257, 88273, 88396, 88498,
        89065, 89440, 89638, 89839, 90150, 90157, 90189, 90191, 90216, 90249, 90258, 90264, 90282, 90334, 90336, 90337,
        90350, 90427, 90712, 90730, 90751, 90770, 90869, 90975, 92087, 93208, 93411, 93869, 94027, 94049, 94351, 94504,
        94699, 94783, 94986, 95035, 96622, 98322, 98482, 98540, 98586, 98722, 98817, 99004, 99055, 99111, 99729, 99763,
        100353, 101373, 101450, 101736, 102185, 103947, 104000, 104831, 105983, 106021, 107158, 107203, 107850, 108698, 108787, 108788,
        109037, 109065, 109522, 109907, 112467, 112720, 112976, 114015, 115766, 116338, 116915, 117375, 117412, 117537, 117557, 117562,
        118114, 118136, 118177, 118240, 118372, 118383, 118389, 118395, 118422, 118548, 118578, 118587, 118590, 118597, 118623, 118720,
        118861, 119032, 119180, 119241, 119263, 119286, 119420, 119486, 119856, 119880, 119990, 120046, 120047, 120607, 120758, 121184,
        121347, 121895, 122077, 122178, 122582, 122935, 123251, 123408, 123573, 123784, 124963, 127020, 127025, 127087, 127879, 128843,
        129666, 129963, 130012, 130214, 130238, 130997, 131098, 131542, 131556, 131696, 131944
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'Method gap fill 2026-11-10: cites IP-Adapter without naming it in the title or abstract'
FROM ip_adapter_excluded
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING ip_adapter_excluded x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING ip_adapter_excluded x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- latent-consistency-model: 39 links, 542 exclusions.
CREATE TEMP TABLE latent_consistency_model_curated ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'latent-consistency-model'
  AND p.id IN (
        20631, 21507, 23134, 23906, 24654, 24775, 24794, 25652, 26587, 26860, 28192, 28359, 28825, 28972, 29385, 29955,
        30081, 30495, 30680, 30946, 31943, 32572, 32876, 33074, 35719, 37002, 40822, 41804, 43569, 43640, 49677, 49988,
        52614, 57876, 59160, 70203, 89212, 90141, 117367
  );

DELETE FROM paper_method_exclusions x
USING latent_consistency_model_curated c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM latent_consistency_model_curated
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM latent_consistency_model_curated
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

CREATE TEMP TABLE latent_consistency_model_excluded ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'latent-consistency-model'
  AND p.id IN (
        15466, 15694, 16277, 17125, 19894, 20332, 20689, 21444, 23396, 23662, 23741, 23799, 23869, 23873, 23916, 24007,
        24059, 24224, 24338, 24474, 24498, 24515, 24638, 24675, 24771, 24800, 24837, 24905, 25012, 25442, 25507, 25621,
        26139, 26333, 27723, 27751, 27774, 28067, 28124, 28217, 28326, 28568, 28625, 28961, 29058, 29060, 29072, 29105,
        29113, 29132, 29275, 29313, 29376, 29417, 29501, 29507, 29746, 29773, 29801, 29824, 29864, 29888, 29989, 30030,
        30539, 30607, 30611, 30623, 30631, 30669, 30746, 30784, 30930, 31023, 31089, 31146, 31149, 31179, 31231, 31297,
        31401, 31525, 31635, 31637, 31719, 31806, 31823, 31843, 31859, 31973, 32039, 32085, 32092, 32093, 32108, 32185,
        32209, 32217, 32295, 32302, 32307, 32397, 32454, 32476, 32669, 32671, 32737, 32776, 32927, 33020, 33149, 33231,
        33265, 33413, 34376, 34397, 34462, 34510, 34835, 34915, 35193, 35448, 35771, 35780, 35877, 36187, 36230, 36243,
        36312, 36338, 36452, 36501, 36546, 36921, 37000, 37066, 37210, 37493, 37677, 37854, 37931, 37983, 38063, 38091,
        38110, 38131, 38178, 38202, 38282, 38395, 38408, 38413, 38451, 38453, 38501, 38592, 38615, 38985, 38989, 39149,
        39176, 39263, 39370, 39492, 39619, 39702, 39764, 39981, 40005, 40208, 40355, 40452, 40483, 40499, 40552, 40586,
        40596, 40733, 40807, 40859, 40875, 40920, 40996, 41006, 41051, 41110, 41155, 41205, 41340, 41421, 41508, 41647,
        41717, 41863, 41980, 41983, 42044, 42045, 42203, 42375, 42843, 43120, 43122, 43260, 43289, 43371, 43446, 43458,
        43603, 43867, 44062, 44340, 44511, 45355, 45418, 45648, 45668, 45714, 45717, 45765, 45802, 45821, 45822, 45990,
        46083, 46342, 46343, 46473, 46483, 46618, 46625, 46644, 46709, 47022, 47186, 47257, 47635, 47809, 47827, 48361,
        48417, 48433, 48478, 48722, 48849, 48984, 49754, 49900, 49926, 49928, 50181, 50320, 50440, 50491, 50547, 50644,
        50664, 50904, 51224, 51235, 51272, 51317, 51406, 51586, 51686, 51687, 51890, 51975, 52354, 52654, 52779, 53059,
        53384, 53449, 53549, 53597, 53862, 53936, 53969, 53993, 54309, 54321, 54419, 54433, 54453, 54511, 54600, 54735,
        54767, 54774, 54971, 55009, 55032, 55549, 55671, 56138, 56312, 56338, 56360, 56369, 56462, 56583, 56692, 56698,
        56756, 56944, 57082, 57083, 57230, 57306, 57460, 57577, 58551, 58966, 59034, 59036, 59113, 59918, 60422, 60871,
        61171, 61229, 61386, 63311, 63430, 63600, 64171, 64467, 64539, 64688, 64906, 65645, 65925, 66384, 66660, 66891,
        66929, 67171, 67319, 67395, 67406, 67417, 68120, 68683, 69137, 69389, 69676, 70863, 70945, 70971, 71093, 71216,
        71288, 71479, 71753, 72214, 72320, 72700, 72704, 72756, 73244, 73602, 73870, 74164, 74273, 74347, 74955, 75528,
        75781, 76467, 77308, 78148, 82847, 82874, 82925, 83182, 83189, 83209, 83684, 83773, 83917, 84225, 84230, 84426,
        84497, 84514, 84627, 84751, 84838, 85017, 85037, 85178, 85409, 85422, 85686, 85748, 85825, 86659, 86804, 87253,
        87567, 87606, 87644, 87782, 87903, 88152, 88153, 88184, 88194, 88253, 88446, 88485, 88752, 89221, 90427, 90449,
        90574, 90597, 90616, 90637, 90687, 90739, 90852, 90988, 91011, 91236, 91308, 91453, 91516, 91832, 92024, 92025,
        92103, 92118, 92140, 92535, 93714, 93925, 94309, 94588, 94883, 94989, 95001, 95056, 95098, 97530, 98038, 98194,
        98408, 98846, 99076, 99105, 99107, 99118, 99210, 99429, 99596, 99814, 99852, 100967, 102585, 102623, 102723, 104043,
        104392, 104585, 105847, 105983, 106425, 106833, 106929, 107009, 107063, 107398, 107658, 108644, 108650, 108730, 109129, 112274,
        112436, 112587, 113029, 113188, 113932, 114018, 115842, 116045, 116117, 116530, 116608, 117716, 117898, 118374, 118405, 118413,
        118430, 118445, 118446, 118452, 118468, 118531, 118543, 118544, 118552, 118560, 118620, 119282, 119430, 120755, 121456, 122022,
        122120, 122290, 122549, 122911, 123053, 123123, 123727, 123757, 125006, 125233, 125516, 126013, 126275, 126603, 127506, 127943,
        128242, 128531, 129051, 129082, 130018, 130449, 131097, 131098, 131297, 131603, 131623, 131882, 131898, 132057
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'Method gap fill 2026-11-10: cites Latent Consistency Models without naming them in the title or abstract'
FROM latent_consistency_model_excluded
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING latent_consistency_model_excluded x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING latent_consistency_model_excluded x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- signed-distance-function: 294 links, 40 exclusions.
CREATE TEMP TABLE signed_distance_function_curated ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'signed-distance-function'
  AND p.id IN (
        1756, 3673, 3736, 6060, 6085, 7582, 8323, 8950, 9218, 9572, 9596, 9842, 10439, 11513, 11598, 11615,
        11819, 11839, 13783, 13815, 13898, 13924, 13978, 13981, 13996, 14037, 14046, 14087, 14280, 14422, 14550, 14655,
        14757, 14929, 14978, 15237, 15318, 15849, 16050, 16248, 16849, 17547, 17883, 18547, 19279, 19284, 19405, 19421,
        19727, 19789, 19868, 19915, 19922, 20159, 20306, 20601, 20949, 20964, 21170, 21219, 22427, 23611, 23616, 23775,
        23777, 24077, 24326, 24336, 24484, 24652, 24803, 24935, 25229, 26390, 26482, 28387, 28766, 28922, 29049, 29125,
        29436, 29527, 32437, 33209, 33751, 34482, 34657, 34963, 35254, 35981, 37057, 37534, 38045, 38462, 39222, 39937,
        40153, 40309, 40473, 40591, 41038, 43942, 44485, 49189, 49517, 51028, 51912, 52008, 54667, 54681, 56572, 58763,
        58895, 58911, 62311, 63436, 63982, 64675, 64730, 64873, 65077, 65447, 67906, 68292, 68423, 68583, 70509, 71384,
        71953, 73052, 74111, 74205, 76295, 76618, 77219, 77297, 78058, 78974, 80234, 81405, 82073, 82318, 83989, 85186,
        85572, 85623, 87675, 87697, 87719, 87869, 88059, 88119, 88416, 90231, 90250, 90255, 90313, 90571, 90592, 90732,
        90755, 90785, 90793, 90872, 90895, 90906, 90911, 91893, 92059, 92283, 94400, 95243, 95272, 95305, 95352, 95696,
        95813, 95844, 95892, 95976, 96122, 96164, 96343, 96355, 96557, 96767, 97000, 97085, 97688, 98556, 99344, 101330,
        101419, 102230, 104385, 104516, 104745, 104753, 104777, 104841, 105381, 105510, 105783, 105807, 105821, 106687, 106769, 107262,
        109473, 112187, 112195, 112199, 112217, 112220, 112390, 112429, 112455, 112534, 112660, 112792, 112840, 113081, 113192, 113195,
        113235, 113419, 113448, 113456, 113470, 113576, 114364, 115258, 115267, 115412, 115502, 115535, 115550, 115562, 115587, 115662,
        115785, 116007, 116146, 116272, 116518, 116566, 116588, 116682, 116706, 116752, 116826, 116828, 116920, 116928, 116999, 117139,
        117162, 117191, 117251, 117298, 117318, 117323, 117394, 117421, 117579, 117612, 117639, 117741, 118089, 118113, 118267, 119045,
        119711, 119713, 119718, 119723, 119745, 119759, 119766, 119789, 119823, 119857, 119900, 120031, 120246, 120526, 120907, 120949,
        121910, 122622, 127417, 128802, 129099, 129344
  );

DELETE FROM paper_method_exclusions x
USING signed_distance_function_curated c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM signed_distance_function_curated
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM signed_distance_function_curated
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

CREATE TEMP TABLE signed_distance_function_excluded ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'signed-distance-function'
  AND p.id IN (
        5950, 6445, 8781, 11616, 11710, 18357, 19625, 23909, 25103, 26877, 28847, 33957, 35106, 56523, 63092, 78520,
        81040, 84934, 85448, 85583, 86895, 86921, 90710, 100524, 101824, 104768, 107921, 108135, 113215, 115959, 116129, 116321,
        116325, 116793, 117541, 118335, 119311, 121739, 127812, 128154
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'Method gap fill 2026-11-10: mentions signed distance functions only in passing or uses unsigned distance fields'
FROM signed_distance_function_excluded
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING signed_distance_function_excluded x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING signed_distance_function_excluded x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- neus: 30 links, 832 exclusions.
CREATE TEMP TABLE neus_curated ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'neus'
  AND p.id IN (
        6060, 9572, 11615, 11907, 12007, 13487, 13901, 13996, 14757, 19221, 20601, 23464, 24173, 25166, 50554, 76739,
        88059, 90755, 96343, 113217, 115848, 117251, 117274, 117277, 119711, 119718, 119723, 120526, 121166, 121540
  );

DELETE FROM paper_method_exclusions x
USING neus_curated c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM neus_curated
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM neus_curated
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

CREATE TEMP TABLE neus_excluded ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'neus'
  AND p.id IN (
        6082, 7368, 7509, 7607, 8781, 8950, 9023, 9218, 9298, 9481, 9560, 9842, 10050, 10499, 10507, 10512,
        10742, 10789, 11016, 11513, 11616, 11755, 11780, 11789, 11971, 12096, 12224, 12267, 12420, 12435, 12788, 12808,
        12957, 13099, 13228, 13287, 13366, 13476, 13733, 13783, 13808, 13815, 13830, 13898, 13924, 13981, 14034, 14037,
        14084, 14087, 14088, 14103, 14104, 14218, 14228, 14255, 14287, 14321, 14325, 14336, 14339, 14392, 14422, 14492,
        14557, 14759, 14822, 14978, 15152, 15188, 15236, 15306, 15348, 15572, 15806, 16691, 16849, 16995, 17220, 17230,
        17465, 17488, 17537, 17547, 17665, 17711, 17883, 17916, 17924, 18146, 18167, 18285, 18420, 18458, 18497, 18638,
        18685, 18721, 18732, 18901, 18952, 18980, 19106, 19247, 19279, 19288, 19421, 19448, 19481, 19580, 19585, 19597,
        19605, 19625, 19757, 19770, 19774, 19789, 19831, 19859, 19893, 19915, 19922, 20112, 20133, 20159, 20175, 20225,
        20232, 20247, 20293, 20301, 20437, 20490, 20561, 20623, 20811, 20931, 20949, 21058, 21252, 21254, 21628, 21637,
        21698, 21794, 21849, 21878, 21913, 22146, 22154, 22204, 22356, 22406, 22427, 22566, 22586, 22760, 22853, 23449,
        23569, 23582, 23616, 23658, 23664, 23767, 23821, 23825, 23830, 23860, 23912, 23998, 24045, 24077, 24079, 24172,
        24178, 24197, 24232, 24241, 24244, 24250, 24315, 24336, 24363, 24449, 24484, 24497, 24504, 24510, 24523, 24558,
        24571, 24602, 24617, 24619, 24634, 24673, 24698, 24700, 24734, 24748, 24776, 24791, 24804, 24812, 24821, 24831,
        24935, 24949, 25053, 25073, 25101, 25145, 25211, 25229, 25281, 25292, 25403, 25491, 25631, 25824, 25899, 25911,
        26000, 26177, 26298, 26305, 26338, 26364, 26366, 26390, 26468, 26519, 26521, 26526, 26534, 26606, 26908, 26986,
        26989, 27373, 27397, 27610, 27636, 27698, 27779, 27817, 27834, 27936, 28037, 28057, 28176, 28287, 28345, 28371,
        28561, 28622, 28661, 28723, 28742, 28813, 28843, 28900, 28919, 28925, 28975, 28983, 29049, 29057, 29069, 29092,
        29130, 29170, 29270, 29388, 29396, 29410, 29436, 29456, 29470, 29495, 29527, 29563, 29570, 29600, 29756, 29793,
        29834, 29854, 29962, 29964, 29965, 30011, 30154, 30256, 30268, 30455, 30462, 30480, 30538, 30540, 30847, 30947,
        30997, 31269, 31340, 31401, 31628, 31802, 31811, 31955, 32032, 32084, 32098, 32110, 32179, 32365, 32437, 32557,
        32642, 32785, 32835, 32845, 32850, 33360, 33604, 33615, 33645, 33665, 33751, 33827, 34052, 34065, 34377, 34394,
        34584, 34706, 34810, 34829, 34963, 35017, 35077, 35106, 35141, 35254, 35272, 35284, 35347, 35592, 35797, 35838,
        35842, 35927, 35980, 36072, 36177, 36186, 36340, 36345, 36510, 36615, 36746, 36808, 37128, 37334, 37496, 37534,
        37694, 37722, 37778, 37813, 37909, 38150, 38268, 38280, 38321, 38456, 38767, 39148, 39222, 39479, 39527, 39574,
        39840, 39851, 39855, 39881, 40073, 40309, 40403, 40413, 40471, 40473, 40591, 40726, 40946, 40992, 41006, 41038,
        41155, 41163, 41250, 41301, 41455, 41626, 41694, 41723, 41816, 41903, 41958, 42122, 42620, 42864, 42971, 43075,
        43217, 44354, 45093, 45203, 45413, 45490, 45728, 45797, 45856, 45893, 46128, 46343, 46363, 46562, 46585, 46607,
        46865, 46871, 47091, 48009, 48364, 48376, 48378, 48562, 48614, 48678, 49769, 50470, 50513, 50525, 50674, 50869,
        51019, 51576, 51736, 51890, 52008, 52024, 52090, 52119, 52125, 52286, 52378, 52504, 52644, 52796, 52881, 52946,
        53282, 53549, 54667, 54937, 55121, 55362, 56718, 56914, 58293, 58895, 59055, 61128, 61395, 62071, 62872, 63348,
        63436, 63683, 63840, 64302, 64641, 64730, 65077, 65424, 65463, 65593, 65771, 66414, 66791, 67058, 68107, 68136,
        68583, 68701, 69339, 69485, 70109, 70147, 70295, 70432, 70509, 70517, 70783, 70797, 71426, 71488, 71574, 72044,
        73271, 73489, 73625, 73942, 74478, 74735, 74960, 75062, 75196, 75405, 75457, 75585, 75704, 76070, 76753, 77219,
        77264, 77393, 77428, 78491, 78956, 79223, 82843, 83698, 84069, 84101, 84148, 84232, 84303, 84318, 84337, 84591,
        84934, 84987, 85160, 85269, 85274, 85404, 85623, 86224, 86275, 86748, 86885, 86893, 86895, 87629, 87647, 87668,
        87761, 87781, 87795, 87864, 87869, 87910, 87925, 87931, 87939, 87973, 87978, 88018, 88099, 88245, 88321, 88416,
        88420, 88478, 88502, 89105, 90210, 90235, 90250, 90255, 90262, 90366, 90379, 90427, 90428, 90559, 90590, 90592,
        90600, 90604, 90650, 90681, 90687, 90702, 90710, 90732, 90741, 90743, 90748, 90785, 90855, 90872, 90895, 90897,
        90911, 90928, 90953, 91430, 92161, 92283, 92443, 93414, 94710, 94776, 94925, 94931, 95792, 96122, 96244, 96518,
        96914, 97200, 97680, 98239, 99674, 101045, 101146, 101381, 102630, 103914, 104190, 104781, 104810, 104817, 104823, 104829,
        104876, 105553, 106424, 106621, 106757, 107152, 107159, 107874, 107926, 108045, 108454, 108753, 109353, 109856, 109858, 109862,
        109866, 109883, 109929, 112184, 112187, 112195, 112354, 112356, 112365, 112455, 112469, 112494, 112526, 112532, 112534, 112558,
        112681, 112683, 112741, 112743, 112750, 112792, 112840, 112863, 112874, 112878, 112912, 112931, 113050, 113051, 113060, 113138,
        113192, 113195, 113234, 113235, 113259, 113293, 113344, 113419, 113456, 113457, 113484, 113692, 114191, 114960, 115258, 115455,
        115463, 115502, 115562, 115576, 115615, 115624, 115649, 115758, 115785, 115796, 115921, 115959, 115988, 116013, 116072, 116095,
        116146, 116210, 116272, 116325, 116350, 116360, 116363, 116409, 116415, 116504, 116514, 116518, 116548, 116566, 116629, 116667,
        116695, 116738, 116752, 116770, 116786, 116793, 116828, 116873, 116886, 116920, 116928, 116930, 116947, 116996, 117027, 117051,
        117095, 117117, 117127, 117139, 117162, 117191, 117207, 117243, 117263, 117268, 117271, 117280, 117282, 117295, 117301, 117321,
        117347, 117357, 117361, 117373, 117392, 117394, 117446, 117541, 117546, 117609, 117617, 117653, 117720, 117892, 118089, 118267,
        118314, 118324, 118703, 119245, 119464, 119707, 119713, 119719, 119745, 119759, 119761, 119766, 119780, 119782, 119784, 119804,
        119808, 119812, 119822, 119823, 119824, 119829, 119838, 119870, 119885, 120031, 120042, 120099, 120116, 120306, 120316, 120390,
        120439, 120499, 121684, 121910, 122285, 122916, 123190, 123375, 124563, 125859, 127020, 127417, 127639, 128802, 129800, 131327
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'Method gap fill 2026-11-10: cites NeuS without naming it, or "NeuS" is part of an unrelated name'
FROM neus_excluded
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING neus_excluded x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING neus_excluded x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- instant-ngp: 81 links, 1705 exclusions.
CREATE TEMP TABLE instant_ngp_curated ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'instant-ngp'
  AND p.id IN (
        11439, 11684, 11907, 12788, 12808, 13182, 13630, 14134, 14218, 14545, 14677, 15234, 15348, 16995, 18255, 18373,
        18458, 18497, 18603, 19486, 19879, 20623, 20634, 20989, 22963, 23777, 24484, 24571, 25288, 25457, 26000, 29813,
        30167, 30767, 31807, 37132, 43093, 46011, 48364, 52200, 57850, 60874, 64676, 67039, 74708, 74735, 75124, 76334,
        85382, 88284, 92443, 93740, 96343, 97220, 101171, 104878, 105479, 105527, 107558, 112448, 112455, 112636, 112637, 112714,
        112858, 112912, 112960, 113622, 113712, 114908, 115455, 115588, 116504, 116852, 117321, 117356, 117486, 121469, 124313, 131008,
        132133
  );

DELETE FROM paper_method_exclusions x
USING instant_ngp_curated c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM instant_ngp_curated
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM instant_ngp_curated
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

CREATE TEMP TABLE instant_ngp_excluded ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'instant-ngp'
  AND p.id IN (
        8462, 9023, 9218, 9298, 9481, 9572, 9941, 10499, 10507, 10512, 10742, 11036, 11080, 11341, 11466, 11513,
        11517, 11521, 11534, 11556, 11579, 11701, 11732, 11780, 11789, 11837, 11969, 11971, 12004, 12007, 12096, 12207,
        12258, 12267, 12319, 12320, 12378, 12420, 12435, 12456, 12490, 12535, 12552, 12821, 12957, 13155, 13218, 13228,
        13287, 13366, 13476, 13487, 13581, 13609, 13637, 13698, 13789, 13815, 13830, 13840, 13870, 13892, 13896, 13900,
        13963, 13978, 14029, 14034, 14037, 14075, 14082, 14088, 14093, 14103, 14104, 14107, 14183, 14228, 14235, 14287,
        14321, 14331, 14384, 14472, 14481, 14483, 14557, 14564, 14633, 14660, 14759, 14770, 14777, 14801, 14822, 14826,
        14848, 14919, 14939, 14978, 15096, 15102, 15152, 15215, 15306, 15335, 15408, 15409, 15432, 15494, 15572, 15580,
        15628, 15859, 16062, 16308, 16336, 16569, 16691, 16845, 16966, 16979, 16985, 17180, 17181, 17185, 17207, 17230,
        17314, 17326, 17465, 17488, 17500, 17501, 17574, 17644, 17665, 17711, 17798, 17924, 18146, 18307, 18420, 18424,
        18449, 18638, 18717, 18721, 18732, 18876, 18901, 19011, 19030, 19062, 19080, 19106, 19221, 19247, 19279, 19288,
        19290, 19315, 19334, 19361, 19366, 19402, 19437, 19520, 19584, 19585, 19597, 19605, 19622, 19625, 19658, 19676,
        19757, 19770, 19774, 19831, 19859, 19893, 19915, 19922, 19965, 20133, 20159, 20163, 20192, 20232, 20255, 20334,
        20358, 20419, 20437, 20441, 20480, 20490, 20522, 20546, 20601, 20674, 20803, 20811, 20876, 20892, 20931, 20964,
        21037, 21044, 21083, 21090, 21252, 21304, 21368, 21377, 21464, 21609, 21622, 21628, 21726, 21752, 21794, 21849,
        21895, 21896, 21912, 21913, 21972, 22007, 22065, 22066, 22123, 22269, 22309, 22356, 22566, 22569, 22570, 22586,
        22643, 22653, 22671, 22747, 22760, 22826, 22946, 23073, 23138, 23171, 23321, 23330, 23390, 23449, 23464, 23468,
        23542, 23569, 23582, 23606, 23616, 23658, 23662, 23664, 23686, 23722, 23726, 23749, 23767, 23769, 23810, 23821,
        23824, 23825, 23855, 23857, 23860, 23885, 23890, 23918, 23922, 23924, 23936, 23938, 23959, 23964, 23980, 23984,
        23986, 23998, 24001, 24008, 24024, 24033, 24075, 24077, 24079, 24088, 24093, 24113, 24120, 24121, 24133, 24152,
        24170, 24183, 24189, 24197, 24223, 24224, 24241, 24244, 24250, 24265, 24282, 24302, 24309, 24311, 24315, 24336,
        24337, 24347, 24349, 24443, 24451, 24454, 24458, 24465, 24482, 24497, 24504, 24510, 24558, 24567, 24602, 24615,
        24617, 24619, 24639, 24673, 24690, 24698, 24700, 24727, 24733, 24734, 24740, 24748, 24774, 24776, 24797, 24803,
        24804, 24812, 24820, 24821, 24831, 24852, 24923, 24932, 24933, 24948, 24949, 24965, 24988, 25034, 25039, 25052,
        25053, 25055, 25062, 25066, 25073, 25077, 25090, 25145, 25156, 25168, 25217, 25231, 25242, 25256, 25281, 25292,
        25362, 25378, 25390, 25415, 25433, 25437, 25486, 25491, 25520, 25574, 25588, 25659, 25676, 25692, 25707, 25728,
        25824, 25923, 25944, 25946, 25948, 25972, 26052, 26173, 26204, 26293, 26338, 26364, 26459, 26521, 26526, 26534,
        26546, 26586, 26595, 26606, 26660, 26667, 26807, 26844, 26852, 26908, 26962, 26977, 26986, 26989, 27005, 27044,
        27060, 27264, 27373, 27397, 27468, 27610, 27694, 27695, 27698, 27816, 27834, 27936, 28016, 28057, 28126, 28140,
        28321, 28345, 28371, 28387, 28493, 28571, 28622, 28661, 28742, 28788, 28857, 28873, 28928, 28968, 28975, 28983,
        28991, 29008, 29019, 29040, 29045, 29056, 29069, 29099, 29114, 29125, 29130, 29136, 29170, 29216, 29270, 29278,
        29281, 29306, 29308, 29359, 29364, 29365, 29388, 29389, 29410, 29431, 29436, 29444, 29456, 29470, 29495, 29497,
        29502, 29506, 29570, 29600, 29618, 29633, 29673, 29750, 29756, 29766, 29770, 29777, 29793, 29834, 29858, 29869,
        29933, 29947, 29972, 29997, 30021, 30044, 30119, 30120, 30146, 30153, 30154, 30169, 30248, 30256, 30268, 30344,
        30359, 30380, 30392, 30515, 30530, 30538, 30540, 30561, 30621, 30649, 30709, 30710, 30756, 30780, 30831, 30847,
        30911, 30924, 30930, 30938, 30947, 30985, 31165, 31365, 31376, 31439, 31457, 31628, 31638, 31660, 31732, 31777,
        31798, 31826, 31849, 31924, 31946, 31950, 32008, 32032, 32084, 32093, 32098, 32117, 32128, 32179, 32181, 32253,
        32301, 32354, 32365, 32436, 32507, 32603, 32608, 32639, 32642, 32712, 32785, 32827, 32835, 32845, 32889, 32890,
        32892, 32898, 32989, 33172, 33209, 33300, 33323, 33523, 33536, 33556, 33589, 33645, 33665, 33740, 33751, 33819,
        33857, 33891, 33997, 34017, 34052, 34065, 34118, 34323, 34347, 34358, 34374, 34377, 34394, 34401, 34405, 34486,
        34572, 34584, 34587, 34633, 34657, 34706, 34798, 34829, 34963, 35017, 35027, 35097, 35141, 35168, 35254, 35272,
        35336, 35353, 35403, 35488, 35612, 35632, 35740, 35829, 35838, 35871, 35927, 35985, 36080, 36128, 36181, 36214,
        36258, 36390, 36396, 36615, 36746, 36765, 36768, 36781, 36784, 36819, 36825, 36856, 36963, 36983, 37057, 37087,
        37226, 37334, 37384, 37470, 37496, 37534, 37659, 37694, 37722, 37778, 38186, 38226, 38244, 38321, 38409, 38631,
        38652, 38714, 38949, 38984, 39015, 39143, 39148, 39222, 39330, 39435, 39498, 39527, 39574, 39581, 39840, 39842,
        39855, 39939, 40060, 40105, 40221, 40252, 40266, 40305, 40372, 40401, 40409, 40431, 40471, 40473, 40520, 40564,
        40591, 40616, 40660, 40702, 40921, 40950, 40987, 41021, 41022, 41025, 41026, 41038, 41045, 41081, 41127, 41149,
        41155, 41156, 41179, 41200, 41244, 41250, 41294, 41312, 41481, 41482, 41626, 41631, 41723, 41785, 41809, 41816,
        41958, 42036, 42319, 42491, 42512, 42568, 42661, 42781, 42866, 43001, 43005, 43075, 43433, 43459, 44157, 44485,
        44645, 45092, 45218, 45490, 45507, 45628, 45724, 45728, 45795, 45844, 45856, 45969, 46030, 46108, 46128, 46206,
        46268, 46278, 46295, 46345, 46429, 46482, 46492, 46524, 46534, 46562, 46585, 46607, 46695, 46775, 46853, 46940,
        46989, 47144, 47193, 47586, 47798, 47871, 47918, 48009, 48322, 48358, 48478, 48519, 48546, 48552, 48562, 49036,
        49069, 49096, 49269, 49319, 49690, 49697, 49910, 50048, 50140, 50470, 50554, 50795, 50994, 51050, 51062, 51281,
        51568, 51653, 51757, 51815, 51848, 51976, 52027, 52090, 52125, 52239, 52286, 52435, 52436, 52504, 52668, 52857,
        52942, 52946, 53021, 53136, 53367, 53398, 53623, 53639, 53647, 54496, 54572, 54627, 54657, 54697, 54716, 55173,
        55294, 55362, 55432, 56255, 56315, 56914, 56930, 57461, 57481, 58334, 58518, 58663, 58728, 58907, 59007, 59055,
        59990, 60254, 60549, 61260, 61268, 61414, 61439, 61686, 62071, 63177, 63390, 63470, 63620, 63682, 63748, 63752,
        63812, 63816, 63857, 63875, 63900, 63901, 63908, 63914, 64045, 64107, 64110, 64300, 64302, 64434, 64505, 64536,
        64641, 64665, 64675, 64709, 64730, 64956, 65220, 65253, 65775, 66120, 66414, 66473, 66703, 67037, 68038, 68064,
        68114, 68136, 68252, 68423, 68503, 68567, 68583, 68660, 68694, 68923, 69101, 69105, 69469, 69620, 69703, 69856,
        69897, 70043, 70068, 70109, 70110, 70147, 70149, 70219, 70262, 70509, 70517, 70550, 70712, 70783, 70784, 70797,
        70887, 71056, 71058, 71060, 71087, 71311, 71426, 71438, 71484, 71488, 71580, 71621, 71709, 71923, 72044, 72126,
        72236, 72271, 72536, 73005, 73057, 73238, 73373, 73409, 73482, 73489, 73536, 73541, 73571, 73625, 73631, 74034,
        74063, 74066, 74109, 74111, 74112, 74165, 74171, 74239, 74372, 74412, 74437, 74478, 74925, 74960, 75062, 75096,
        75155, 75182, 75289, 75337, 75457, 75566, 75585, 75699, 75706, 75843, 75926, 76019, 76028, 76070, 76143, 76753,
        76817, 76866, 76922, 76984, 77264, 77383, 77388, 77393, 77419, 77426, 77428, 77448, 77468, 77757, 77788, 77956,
        78058, 78106, 78164, 78186, 78220, 78491, 78538, 78603, 79180, 79223, 79230, 79533, 79730, 79929, 83465, 83989,
        84020, 84108, 84131, 84165, 84188, 84222, 84232, 84257, 84271, 84303, 84311, 84337, 84359, 84399, 84406, 84416,
        84456, 84473, 84475, 84477, 84493, 84509, 84591, 84622, 84625, 84644, 84675, 84684, 84692, 84720, 84804, 84868,
        84883, 84937, 84977, 84987, 85002, 85018, 85152, 85160, 85165, 85174, 85222, 85232, 85246, 85254, 85258, 85269,
        85274, 85295, 85345, 85369, 85385, 85400, 85442, 85494, 85539, 85554, 85556, 85596, 85730, 85898, 85928, 86224,
        86275, 86296, 86347, 86462, 86618, 86707, 86725, 86748, 86849, 86870, 86893, 87057, 87551, 87562, 87580, 87613,
        87647, 87668, 87691, 87714, 87715, 87743, 87754, 87774, 87781, 87823, 87831, 87864, 87869, 87916, 87931, 87939,
        87994, 88033, 88059, 88090, 88093, 88105, 88141, 88226, 88245, 88267, 88321, 88366, 88377, 88385, 88388, 88420,
        88435, 88452, 88462, 88478, 88489, 88512, 88518, 89187, 89846, 89961, 90049, 90095, 90098, 90194, 90196, 90206,
        90210, 90231, 90235, 90255, 90262, 90271, 90293, 90316, 90319, 90320, 90361, 90365, 90368, 90379, 90384, 90415,
        90428, 90437, 90447, 90457, 90475, 90479, 90480, 90532, 90535, 90559, 90564, 90566, 90573, 90590, 90592, 90603,
        90615, 90621, 90683, 90698, 90710, 90732, 90736, 90741, 90748, 90755, 90766, 90776, 90785, 90822, 90823, 90859,
        90895, 90897, 90912, 90920, 90922, 90940, 90953, 90966, 90976, 90985, 90999, 91008, 91077, 91341, 91430, 91502,
        91621, 91626, 91742, 91942, 91948, 91965, 91974, 92045, 92059, 92161, 92192, 92426, 92542, 93242, 93253, 93414,
        93534, 94032, 94210, 94271, 94316, 94451, 94469, 94471, 94558, 94583, 94710, 94714, 94776, 94789, 94793, 94825,
        94839, 94925, 95152, 95337, 95497, 95549, 95765, 95792, 96055, 96110, 96122, 96142, 96209, 96323, 96335, 96518,
        96720, 96908, 96914, 97466, 97531, 97655, 98239, 98558, 98598, 98606, 98958, 99212, 99674, 99962, 100148, 100343,
        100393, 101708, 103897, 103898, 103903, 103912, 103913, 103914, 104013, 104065, 104482, 104516, 104725, 104745, 104753, 104781,
        104782, 104814, 104823, 104835, 104839, 104842, 104853, 104876, 104879, 105135, 105539, 105952, 106408, 106467, 106478, 106527,
        106558, 106630, 106639, 106757, 106788, 107173, 107186, 107226, 107678, 107844, 107926, 108197, 108289, 108293, 108420, 108436,
        108454, 108512, 108520, 108657, 108729, 108753, 108778, 109482, 109856, 109858, 109862, 109863, 109866, 109868, 109871, 109876,
        109883, 109886, 109899, 109902, 109905, 109918, 109919, 109929, 109932, 109933, 112176, 112184, 112187, 112219, 112221, 112243,
        112251, 112256, 112275, 112312, 112313, 112319, 112332, 112356, 112366, 112444, 112472, 112480, 112488, 112494, 112499, 112506,
        112526, 112534, 112543, 112549, 112557, 112570, 112601, 112663, 112675, 112677, 112704, 112709, 112717, 112721, 112724, 112743,
        112774, 112782, 112792, 112820, 112840, 112852, 112853, 112857, 112863, 112874, 112878, 112882, 112890, 112897, 112987, 113017,
        113050, 113051, 113060, 113071, 113123, 113138, 113155, 113166, 113217, 113226, 113232, 113235, 113236, 113243, 113259, 113283,
        113293, 113365, 113388, 113414, 113456, 113457, 113484, 113486, 113503, 113515, 113529, 113532, 113561, 113580, 113588, 113623,
        113629, 113701, 113827, 113978, 114437, 115010, 115030, 115234, 115463, 115493, 115533, 115546, 115562, 115571, 115576, 115579,
        115583, 115587, 115608, 115624, 115662, 115698, 115762, 115775, 115785, 115796, 115830, 115838, 115870, 115871, 115913, 115921,
        115931, 115959, 116084, 116094, 116095, 116114, 116129, 116134, 116146, 116161, 116177, 116210, 116257, 116270, 116272, 116305,
        116350, 116360, 116372, 116390, 116409, 116414, 116415, 116474, 116495, 116518, 116523, 116544, 116548, 116601, 116602, 116606,
        116667, 116695, 116729, 116738, 116752, 116765, 116770, 116780, 116786, 116793, 116832, 116834, 116881, 116910, 116920, 116928,
        116930, 116938, 116961, 116996, 117027, 117032, 117043, 117051, 117067, 117087, 117089, 117091, 117095, 117107, 117117, 117119,
        117157, 117186, 117191, 117207, 117208, 117212, 117236, 117243, 117244, 117252, 117262, 117266, 117268, 117273, 117274, 117277,
        117280, 117284, 117297, 117305, 117308, 117314, 117340, 117353, 117357, 117368, 117392, 117413, 117424, 117470, 117476, 117478,
        117487, 117523, 117527, 117530, 117531, 117541, 117546, 117548, 117576, 117579, 117582, 117588, 117592, 117594, 117609, 117611,
        117615, 117617, 117626, 117631, 117635, 117636, 117650, 117653, 117683, 117711, 117720, 117775, 117892, 118242, 118248, 118277,
        118314, 118324, 119100, 119194, 119196, 119308, 119707, 119713, 119718, 119745, 119752, 119768, 119780, 119782, 119784, 119804,
        119808, 119809, 119812, 119817, 119820, 119823, 119838, 119885, 120077, 120119, 120127, 120133, 120183, 120306, 120313, 120316,
        120467, 120499, 120526, 120632, 120704, 120787, 120927, 121009, 121177, 121288, 121347, 121588, 121620, 121654, 121700, 121829,
        121910, 121916, 122365, 122883, 123999, 124081, 124123, 124277, 125276, 125726, 125859, 125982, 126279, 126566, 127117, 127331,
        127639, 128432, 129397, 129800, 130498, 130499, 130642, 131408, 131921
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'Method gap fill 2026-11-10: cites Instant-NGP without naming it or hash encodings in the title or abstract'
FROM instant_ngp_excluded
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING instant_ngp_excluded x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING instant_ngp_excluded x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- triplane: 121 links, 7 exclusions.
CREATE TEMP TABLE triplane_curated ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'triplane'
  AND p.id IN (
        3201, 7509, 11709, 13614, 14039, 14467, 16248, 18373, 19011, 19436, 20436, 20601, 20917, 21219, 23321, 23390,
        24036, 24045, 24289, 24472, 24504, 24773, 24797, 25257, 25728, 25824, 25944, 26005, 26137, 26482, 26606, 28371,
        28561, 28858, 28991, 29190, 29723, 29778, 30006, 30538, 31340, 31625, 31703, 32453, 32557, 32989, 34334, 34377,
        37608, 38186, 39090, 40160, 40292, 40889, 41876, 42609, 43433, 45915, 46046, 46539, 46750, 46775, 46865, 49418,
        52453, 54771, 67039, 67719, 68576, 68694, 73886, 74708, 76234, 78164, 86247, 87939, 88033, 88416, 90264, 90350,
        90494, 90698, 90726, 93242, 94805, 94994, 95281, 97442, 104975, 106786, 108439, 112968, 112987, 113050, 113104, 113172,
        113321, 113365, 113478, 113506, 115594, 116072, 116134, 116504, 116524, 116718, 117250, 117300, 117383, 117642, 117761, 117939,
        119900, 120132, 120347, 120374, 120913, 121840, 121896, 125960, 130060
  );

DELETE FROM paper_method_exclusions x
USING triplane_curated c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM triplane_curated
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM triplane_curated
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

CREATE TEMP TABLE triplane_excluded ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'triplane'
  AND p.id IN (
        34017, 35981, 46940, 63724, 63812, 115385, 116012
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'Method gap fill 2026-11-10: mentions tri-planes only in passing, as a contrast, or in another sense'
FROM triplane_excluded
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING triplane_excluded x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING triplane_excluded x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- structure-from-motion: 203 links, 21 exclusions.
CREATE TEMP TABLE structure_from_motion_curated ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'structure-from-motion'
  AND p.id IN (
        2082, 2751, 2866, 3482, 6191, 11513, 11591, 12320, 13601, 15572, 17181, 17458, 17465, 17816, 18716, 20128,
        22342, 23936, 24113, 24464, 24639, 25911, 27816, 28793, 29677, 30561, 30649, 30709, 31368, 32306, 32608, 33161,
        33722, 34443, 34618, 36571, 36995, 39143, 40060, 41081, 43644, 43924, 45275, 45715, 46343, 46562, 46997, 48017,
        48120, 48545, 51842, 53021, 58493, 58989, 59078, 59556, 59687, 60192, 61026, 61239, 63914, 64536, 64662, 64837,
        66222, 66265, 66390, 68304, 69207, 70887, 71621, 71735, 73489, 73571, 73696, 74359, 74953, 75088, 76739, 77419,
        79732, 84232, 84266, 84336, 84518, 84580, 84610, 84626, 84762, 85175, 85400, 85448, 85539, 85547, 85572, 86375,
        87042, 87613, 87629, 87920, 88032, 88142, 88508, 90208, 90222, 90303, 90384, 90385, 90398, 90855, 92546, 95873,
        95920, 96132, 96515, 96518, 96672, 97208, 97493, 97548, 97678, 103900, 105154, 109481, 109482, 109873, 109877, 112379,
        112506, 112510, 112860, 112871, 112915, 113067, 113236, 113580, 113604, 113643, 114890, 114952, 115554, 115763, 115908, 115951,
        116114, 116335, 116384, 116385, 116446, 116489, 116625, 116886, 117302, 117328, 117340, 117348, 117350, 117555, 117603, 117658,
        118242, 118253, 118269, 118349, 119326, 119567, 119819, 119884, 119952, 120099, 120115, 120124, 120154, 120205, 120315, 120450,
        120487, 120551, 120558, 120565, 120685, 121033, 121091, 121111, 121282, 121346, 121506, 121551, 121685, 121932, 124123, 124683,
        125151, 126160, 126606, 127231, 127290, 129856, 130257, 130584, 131565, 131852, 131867
  );

DELETE FROM paper_method_exclusions x
USING structure_from_motion_curated c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM structure_from_motion_curated
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM structure_from_motion_curated
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

CREATE TEMP TABLE structure_from_motion_excluded ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'structure-from-motion'
  AND p.id IN (
        14082, 18423, 21464, 24690, 32436, 38512, 41521, 44868, 50572, 51381, 81873, 85066, 85446, 105150, 109353, 116676,
        119780, 120034, 121288, 122612, 123803
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'Method gap fill 2026-11-10: mentions structure from motion only in passing or as the step it removes'
FROM structure_from_motion_excluded
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING structure_from_motion_excluded x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING structure_from_motion_excluded x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- multi-view-stereo: 107 links, 15 exclusions.
CREATE TEMP TABLE multi_view_stereo_curated ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'multi-view-stereo'
  AND p.id IN (
        2849, 4655, 5609, 7459, 8950, 13366, 13644, 13681, 13853, 14325, 15046, 15402, 15660, 17330, 17547, 18359,
        19080, 19339, 21637, 22830, 25101, 25166, 26105, 26298, 27816, 29049, 30257, 34963, 35077, 40060, 40651, 40681,
        40861, 41269, 43439, 46343, 48376, 50554, 51842, 58466, 60316, 60381, 64426, 64451, 65051, 67848, 68304, 69310,
        70764, 70887, 79885, 80340, 81405, 84266, 84731, 87803, 88215, 90501, 90690, 90849, 90855, 95302, 96920, 97298,
        97327, 103904, 103908, 109468, 109469, 109470, 109471, 109472, 109473, 109474, 109475, 109476, 109483, 109484, 109485, 109487,
        109488, 109489, 109490, 112578, 113017, 113067, 113217, 113296, 113466, 113995, 115662, 115848, 116015, 116514, 116920, 117271,
        117280, 117298, 117301, 117336, 118349, 119777, 121017, 121829, 123911, 125029, 128500
  );

DELETE FROM paper_method_exclusions x
USING multi_view_stereo_curated c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM multi_view_stereo_curated
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM multi_view_stereo_curated
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

CREATE TEMP TABLE multi_view_stereo_excluded ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'multi-view-stereo'
  AND p.id IN (
        11837, 14248, 15733, 19279, 20949, 32179, 37212, 41697, 46262, 50572, 51872, 80053, 88310, 106621, 116414
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'Method gap fill 2026-11-10: mentions multi-view stereo only in passing or as a dataset name'
FROM multi_view_stereo_excluded
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING multi_view_stereo_excluded x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING multi_view_stereo_excluded x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- task-arithmetic: 97 links, 517 exclusions.
CREATE TEMP TABLE task_arithmetic_curated ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'task-arithmetic'
  AND p.id IN (
        11857, 15885, 21366, 22217, 23404, 23650, 24582, 26569, 27537, 31249, 31303, 32350, 33098, 33494, 34077, 34399,
        37514, 38050, 39658, 42411, 43787, 45371, 45737, 46799, 46913, 47166, 50908, 51346, 51501, 52353, 52607, 52623,
        53429, 53821, 56679, 57588, 57636, 58580, 58798, 58889, 59780, 60404, 66616, 66877, 67360, 67593, 69337, 70379,
        71860, 73297, 75679, 75690, 76524, 76646, 83135, 83402, 84313, 84841, 85755, 86036, 86801, 87068, 89103, 89182,
        89374, 89866, 91000, 91955, 92790, 93204, 94067, 94926, 99141, 99190, 100452, 100906, 100966, 101661, 101926, 106212,
        107549, 110437, 111809, 113325, 118166, 118210, 122086, 125035, 126406, 126825, 127076, 127494, 128102, 128230, 130267, 131074,
        131995
  );

DELETE FROM paper_method_exclusions x
USING task_arithmetic_curated c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM task_arithmetic_curated
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM task_arithmetic_curated
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

CREATE TEMP TABLE task_arithmetic_excluded ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'task-arithmetic'
  AND p.id IN (
        11784, 11968, 12134, 12199, 12902, 13255, 13300, 13928, 14989, 15243, 15920, 16034, 16797, 16873, 17019, 17108,
        17777, 17942, 18075, 18222, 18607, 18767, 19716, 20037, 20357, 21104, 21227, 21238, 21548, 21660, 21889, 22115,
        22126, 22135, 22431, 22438, 22987, 23134, 23197, 23801, 24427, 24641, 24977, 25123, 25408, 25456, 25492, 26141,
        26510, 26750, 26788, 27069, 27086, 27287, 27621, 27822, 27843, 27951, 27953, 27999, 28002, 28101, 28446, 28683,
        29071, 29160, 29385, 29616, 29864, 30262, 30367, 30386, 30460, 30473, 30881, 31013, 31219, 31253, 31400, 31495,
        31547, 31600, 31617, 31823, 31908, 32056, 32331, 32448, 32732, 32903, 33032, 33070, 33194, 33441, 33493, 33567,
        33597, 33694, 33759, 34053, 34343, 34456, 34767, 35004, 35174, 35569, 35588, 35776, 35811, 35844, 35854, 35946,
        36333, 36553, 37279, 37412, 37515, 37637, 37669, 37756, 37885, 37906, 37984, 38054, 38091, 38143, 38187, 38194,
        38218, 38350, 38465, 38508, 38618, 38753, 38765, 38833, 38843, 38996, 39002, 39482, 39754, 39782, 39998, 40102,
        40288, 41139, 41554, 41561, 41692, 42208, 42245, 42315, 42511, 42698, 43546, 43651, 43832, 44004, 44051, 44220,
        44229, 44763, 44882, 44915, 45289, 46211, 46766, 46839, 47032, 47142, 47408, 47485, 47809, 48148, 48339, 48524,
        48539, 48797, 48924, 48990, 49050, 49137, 49187, 49213, 49235, 49370, 49619, 49679, 50913, 51462, 51797, 52382,
        52658, 52916, 53106, 53271, 53285, 53760, 54216, 54916, 54988, 55159, 55391, 55399, 55730, 55894, 55969, 56057,
        56081, 56505, 56567, 56783, 57064, 57112, 57193, 57263, 57357, 57380, 57386, 57415, 57561, 57891, 58696, 58710,
        58783, 59823, 59860, 59904, 60521, 60591, 60731, 60745, 60829, 61085, 61104, 61127, 61169, 61197, 61236, 61245,
        61249, 61320, 62070, 62312, 62658, 63109, 64096, 64633, 65587, 66155, 66346, 66351, 66711, 66919, 66920, 67702,
        67836, 68408, 68424, 68799, 68866, 69131, 69309, 69360, 69559, 70071, 70226, 70640, 70909, 71634, 71763, 71961,
        72013, 72472, 72556, 72568, 72783, 72881, 72937, 73004, 73051, 73527, 73944, 74614, 74830, 75666, 75893, 76017,
        76031, 76047, 76075, 76121, 76267, 76865, 77178, 77195, 82896, 82972, 83169, 83507, 84161, 84572, 84721, 84737,
        84767, 84875, 85147, 85148, 85285, 85773, 85896, 86332, 86350, 86448, 86493, 86654, 86909, 87172, 87247, 87272,
        87343, 87380, 87728, 88016, 88801, 88947, 89233, 89257, 89694, 89848, 89908, 89909, 89964, 89990, 90149, 90157,
        90256, 90506, 90711, 90725, 90727, 90817, 90950, 91125, 91381, 91544, 91576, 91664, 91973, 92010, 92137, 92472,
        92561, 92644, 92735, 92745, 92841, 93367, 93399, 93420, 93427, 93430, 93487, 93520, 93607, 93700, 93719, 93868,
        93904, 93932, 93976, 94002, 94195, 94277, 94286, 94483, 94561, 94620, 94791, 95096, 98323, 98846, 98887, 98985,
        99039, 99078, 99099, 99314, 99489, 99606, 99679, 99706, 99736, 99820, 99824, 100165, 100230, 100331, 100345, 100563,
        100578, 100636, 100738, 100755, 100778, 100831, 100885, 100917, 101008, 101297, 101372, 101546, 101653, 101940, 101985, 102091,
        102230, 102281, 102346, 102785, 103426, 103714, 103864, 104051, 104452, 104536, 104560, 105401, 105646, 106098, 106250, 106255,
        106291, 106321, 106342, 108374, 108781, 108939, 108974, 108983, 109118, 109355, 110058, 111085, 111895, 112097, 112551, 113336,
        113971, 114944, 116751, 118147, 118148, 118170, 118180, 118231, 119445, 121951, 122100, 122252, 122288, 122314, 122316, 122376,
        122379, 122471, 122656, 122676, 122688, 122692, 122731, 122874, 122979, 123506, 123508, 123553, 123556, 124136, 124206, 124209,
        124213, 124428, 124434, 124549, 124577, 124813, 124824, 125259, 125498, 125529, 125544, 126023, 126024, 126595, 126765, 126954,
        127316, 127700, 127926, 128276, 128335, 128386, 128662, 128667, 128703, 128946, 129118, 129214, 129597, 129753, 129829, 129972,
        130022, 130800, 131879, 131985, 132071
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'Method gap fill 2026-11-10: cites Task Arithmetic without naming it, or uses in-context-learning task vectors'
FROM task_arithmetic_excluded
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING task_arithmetic_excluded x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING task_arithmetic_excluded x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- ties-merging: 8 links, 435 exclusions.
CREATE TEMP TABLE ties_merging_curated ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'ties-merging'
  AND p.id IN (
        16873, 37885, 38288, 46825, 57588, 82972, 83402, 85896
  );

DELETE FROM paper_method_exclusions x
USING ties_merging_curated c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM ties_merging_curated
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM ties_merging_curated
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

CREATE TEMP TABLE ties_merging_excluded ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'ties-merging'
  AND p.id IN (
        18607, 23404, 23650, 24582, 24641, 27069, 27086, 27951, 27999, 28683, 28801, 29160, 29616, 29864, 30080, 30386,
        30654, 30824, 30881, 31249, 31253, 31303, 31400, 31495, 31550, 31578, 31600, 31617, 31893, 32056, 32511, 32690,
        32732, 33098, 33154, 33194, 33421, 33493, 33494, 33597, 33694, 33870, 33970, 34053, 34077, 34160, 34315, 34343,
        34456, 34509, 35007, 35588, 35697, 35811, 35844, 35854, 36245, 36314, 36333, 36509, 36606, 36852, 37279, 37514,
        37637, 37669, 37756, 37906, 37984, 38050, 38143, 38194, 38218, 38299, 38465, 38618, 38704, 38753, 38765, 38833,
        39002, 39658, 39782, 39998, 41139, 41554, 41561, 41646, 41977, 42208, 42245, 42411, 43421, 43832, 43882, 44051,
        44220, 44229, 44246, 44300, 44443, 44915, 45035, 45289, 45371, 45497, 45547, 45737, 46079, 46211, 46766, 46799,
        46839, 46913, 47032, 47260, 47468, 47485, 47609, 47995, 48236, 48396, 48539, 48738, 48797, 48865, 48887, 48924,
        49102, 49104, 49235, 49370, 49388, 49524, 49619, 49775, 49818, 50173, 51103, 51462, 51501, 51578, 51797, 51816,
        52353, 52382, 52391, 52607, 52695, 52916, 53194, 53588, 53657, 53821, 54016, 54216, 54590, 54988, 55159, 55391,
        55730, 55948, 56057, 56675, 56732, 57112, 57380, 57415, 57636, 57891, 57927, 58696, 58783, 58798, 58980, 58986,
        59780, 59858, 60404, 60484, 60731, 60745, 61152, 61197, 61236, 61245, 61320, 61624, 62070, 62312, 62447, 62658,
        63946, 64096, 64633, 65154, 65587, 66346, 66351, 66403, 66711, 66877, 66920, 67208, 67360, 67593, 67793, 67951,
        68323, 68408, 68424, 68465, 68866, 68968, 69131, 69329, 69337, 69351, 69360, 69546, 69559, 70136, 70224, 70226,
        70379, 70717, 70974, 71763, 71860, 72272, 72472, 72556, 72568, 72881, 72937, 73051, 73297, 74614, 75679, 75690,
        76017, 76031, 76068, 76075, 76267, 76524, 76865, 77195, 83135, 83169, 83875, 84141, 84161, 84313, 84525, 84572,
        84721, 84737, 84767, 84841, 84875, 85147, 85148, 85755, 85773, 86036, 86158, 86654, 86801, 87068, 87151, 87172,
        87247, 87728, 88016, 89182, 89257, 89374, 89694, 89866, 89945, 89963, 89964, 90020, 90149, 90711, 90727, 90950,
        91000, 91049, 91125, 91576, 92468, 92472, 92559, 92620, 92644, 92745, 92841, 93204, 93367, 93420, 93430, 93460,
        93502, 93700, 93904, 93932, 94067, 94277, 94286, 94513, 94561, 94791, 94919, 94926, 95096, 98846, 98887, 99021,
        99039, 99099, 99141, 99190, 99314, 99606, 99736, 99820, 99824, 100230, 100331, 100371, 100452, 100636, 100738, 100755,
        100831, 100906, 101126, 101280, 101546, 101653, 101661, 101985, 102205, 102346, 102461, 102570, 102889, 103092, 103714, 104051,
        104452, 104536, 104771, 105401, 105595, 105646, 106255, 106291, 106321, 107228, 107549, 107727, 107959, 108383, 108571, 108781,
        108791, 108939, 108974, 108983, 109088, 109530, 109717, 110347, 110733, 110817, 110861, 110938, 111085, 111809, 111895, 112097,
        113870, 113936, 114206, 118147, 118148, 118150, 118166, 118170, 118180, 118210, 118231, 119445, 121951, 122376, 122379, 122443,
        122676, 122874, 123508, 123553, 123674, 123874, 124213, 124434, 124549, 124661, 124824, 125035, 125259, 126023, 126024, 126406,
        126595, 126765, 127316, 128102, 128230, 128276, 128386, 128667, 128703, 129214, 129597, 129972, 130022, 130267, 130491, 130800,
        131879, 131995, 132071
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'Method gap fill 2026-11-10: cites TIES-Merging without naming it in the title or abstract'
FROM ties_merging_excluded
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING ties_merging_excluded x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING ties_merging_excluded x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- dare: 7 links, 371 exclusions.
CREATE TEMP TABLE dare_curated ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'dare'
  AND p.id IN (
        22987, 33123, 38288, 38350, 38753, 82972, 102983
  );

DELETE FROM paper_method_exclusions x
USING dare_curated c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM dare_curated
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM dare_curated
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

CREATE TEMP TABLE dare_excluded ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'dare'
  AND p.id IN (
        22743, 23341, 23650, 23668, 24511, 24582, 26155, 26788, 27380, 27393, 27475, 27537, 27641, 27951, 28683, 29160,
        29168, 29864, 29990, 30080, 30409, 30460, 30654, 30789, 30824, 30881, 31022, 31038, 31303, 31495, 31512, 31578,
        31855, 31893, 32056, 32527, 32690, 32732, 32846, 33098, 33194, 33256, 33308, 33421, 33463, 33493, 33597, 33694,
        34053, 34160, 34315, 34509, 34768, 35004, 35007, 35588, 35844, 35854, 36314, 36333, 36519, 36606, 36852, 37412,
        37637, 37656, 37669, 37756, 37885, 37906, 38067, 38218, 38454, 38465, 38618, 38704, 38727, 38728, 38765, 38833,
        38890, 39002, 39499, 41139, 41554, 41561, 41594, 41646, 41977, 42208, 42226, 42411, 43421, 43535, 43651, 43832,
        43882, 44136, 44210, 44220, 44229, 44242, 44246, 44247, 44300, 44305, 44435, 44443, 44763, 44866, 44915, 45289,
        45303, 45332, 45371, 45547, 45737, 45973, 46766, 46799, 46825, 46839, 46913, 47032, 47408, 47485, 47995, 48271,
        48400, 48539, 48797, 48865, 48924, 49102, 49370, 49524, 49534, 49619, 49775, 50386, 50908, 51030, 51462, 51501,
        51561, 52181, 52382, 52607, 52623, 52916, 53437, 53570, 53588, 53760, 53819, 53821, 54016, 54216, 54590, 54956,
        54988, 55159, 55420, 55730, 56057, 57112, 57121, 57431, 57588, 57891, 58798, 58980, 58986, 59780, 59858, 60424,
        60484, 60731, 61083, 61197, 61236, 61624, 61720, 62070, 62447, 62658, 62696, 62774, 63617, 64096, 64633, 66166,
        66346, 66351, 66403, 66711, 67360, 67793, 67951, 68323, 68408, 68424, 68866, 69131, 69329, 69337, 69618, 69906,
        70136, 70156, 70224, 70226, 71184, 72272, 72305, 72472, 72556, 72881, 72937, 73051, 73467, 74316, 75679, 75690,
        76031, 76068, 76267, 76524, 76865, 83135, 83169, 83402, 84161, 84572, 84721, 84737, 84767, 85003, 85147, 85148,
        85755, 85773, 85896, 86036, 86158, 86493, 86519, 87068, 87151, 87247, 87450, 87728, 88943, 89257, 89694, 89866,
        90488, 90719, 90950, 91125, 91381, 91664, 92472, 92559, 92841, 93204, 93420, 93430, 93460, 93745, 93932, 94180,
        94286, 94561, 94791, 94919, 94926, 95096, 98773, 98887, 99021, 99039, 99078, 99099, 99141, 99190, 99314, 99736,
        99820, 99824, 100230, 100755, 100831, 100910, 101126, 101280, 101546, 101661, 101985, 102799, 102895, 102951, 103066, 103092,
        103102, 103147, 103321, 103539, 103714, 103758, 104051, 104536, 105401, 105646, 106255, 106321, 107228, 108383, 108473, 108939,
        108974, 109088, 109530, 109765, 110102, 110143, 110145, 110347, 110437, 110499, 110676, 110733, 110743, 110817, 110861, 110938,
        111085, 118146, 118147, 118166, 118170, 118180, 118210, 121951, 122376, 122379, 122443, 122731, 122874, 123553, 124549, 124824,
        125035, 126023, 126406, 126595, 126765, 127316, 128102, 128230, 128276, 128667, 128703, 129214, 129597, 130022, 130267, 130800,
        131879, 131995, 132071
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'Method gap fill 2026-11-10: cites DARE without naming it in the title or abstract'
FROM dare_excluded
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING dare_excluded x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING dare_excluded x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;


-- Hero image credits (images imported with import_entity_image.py).
UPDATE methods SET image_credit = '[DreamBooth: Fine Tuning Text-to-Image Diffusion Models for Subject-Driven Generation](/paper/2208.12242)' WHERE slug = 'dreambooth';
UPDATE methods SET image_credit = '[An Image is Worth One Word: Personalizing Text-to-Image Generation using Textual Inversion](/paper/2208.01618)' WHERE slug = 'textual-inversion';
UPDATE methods SET image_credit = '[IP-Adapter: Text Compatible Image Prompt Adapter for Text-to-Image Diffusion Models](/paper/2308.06721)' WHERE slug = 'ip-adapter';
UPDATE methods SET image_credit = '[Latent Consistency Models: Synthesizing High-Resolution Images with Few-Step Inference](/paper/2310.04378)' WHERE slug = 'latent-consistency-model';
UPDATE methods SET image_credit = '[DeepSDF: Learning Continuous Signed Distance Functions for Shape Representation](/paper/1901.05103)' WHERE slug = 'signed-distance-function';
UPDATE methods SET image_credit = '[NeuS: Learning Neural Implicit Surfaces by Volume Rendering for Multi-view Reconstruction](/paper/2106.10689)' WHERE slug = 'neus';
UPDATE methods SET image_credit = '[Instant Neural Graphics Primitives with a Multiresolution Hash Encoding](/paper/2201.05989)' WHERE slug = 'instant-ngp';
UPDATE methods SET image_credit = '[Efficient Geometry-aware 3D Generative Adversarial Networks](/paper/2112.07945)' WHERE slug = 'triplane';
UPDATE methods SET image_credit = '[Structure-from-Motion Revisited](/paper/109481)' WHERE slug = 'structure-from-motion';
UPDATE methods SET image_credit = '[MVSNet: Depth Inference for Unstructured Multi-view Stereo](/paper/1804.02505)' WHERE slug = 'multi-view-stereo';
UPDATE methods SET image_credit = '[Editing Models with Task Arithmetic](/paper/2212.04089)' WHERE slug = 'task-arithmetic';
UPDATE methods SET image_credit = '[TIES-Merging: Resolving Interference When Merging Models](/paper/2306.01708)' WHERE slug = 'ties-merging';
UPDATE methods SET image_credit = '[Language Models are Super Mario: Absorbing Abilities from Homologous Models as a Free Lunch](/paper/2311.03099)' WHERE slug = 'dare';

-- Source evidence protects each Introduced link from automated removal.
INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source' FROM methods
WHERE slug IN ('dreambooth', 'textual-inversion', 'ip-adapter', 'latent-consistency-model', 'neus', 'instant-ngp', 'task-arithmetic', 'ties-merging', 'dare')
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
