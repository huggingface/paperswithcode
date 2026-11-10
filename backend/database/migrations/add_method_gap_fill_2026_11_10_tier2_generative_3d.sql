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
    'dreambooth',
    'DreamBooth',
    'DreamBooth',
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
    image_url = EXCLUDED.image_url,
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
    image_url = EXCLUDED.image_url,
    abstract_linking = EXCLUDED.abstract_linking,
    aliases = EXCLUDED.aliases,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, image_credit, abstract_linking, aliases
)
VALUES (
    'ip-adapter',
    'IP-Adapter',
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
    image_url = EXCLUDED.image_url,
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
    image_url = EXCLUDED.image_url,
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
    image_url = EXCLUDED.image_url,
    abstract_linking = EXCLUDED.abstract_linking,
    aliases = EXCLUDED.aliases,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, image_credit, abstract_linking, aliases
)
VALUES (
    'neus',
    'NeuS',
    'NeuS',
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
    image_url = EXCLUDED.image_url,
    abstract_linking = EXCLUDED.abstract_linking,
    aliases = EXCLUDED.aliases,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, image_credit, abstract_linking, aliases
)
VALUES (
    'instant-ngp',
    'Instant-NGP',
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
    image_url = EXCLUDED.image_url,
    abstract_linking = EXCLUDED.abstract_linking,
    aliases = EXCLUDED.aliases,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, image_credit, abstract_linking, aliases
)
VALUES (
    'triplane',
    'Triplane',
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
    image_url = EXCLUDED.image_url,
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
    image_url = EXCLUDED.image_url,
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
    image_url = EXCLUDED.image_url,
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
    image_url = EXCLUDED.image_url,
    abstract_linking = EXCLUDED.abstract_linking,
    aliases = EXCLUDED.aliases,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, image_credit, abstract_linking, aliases
)
VALUES (
    'ties-merging',
    'TIES-Merging',
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
    image_url = EXCLUDED.image_url,
    abstract_linking = EXCLUDED.abstract_linking,
    aliases = EXCLUDED.aliases,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, image_credit, abstract_linking, aliases
)
VALUES (
    'dare',
    'DARE',
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
    image_url = EXCLUDED.image_url,
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
        10140, -- 2208.12242 DreamBooth: Fine Tuning Text-to-Image Diffusion Models for Subject-Dri
        13928, -- 2303.11305 SVDiff: Compact Parameter Space for Diffusion Fine-Tuning
        14071, -- 2303.13508 DreamBooth3D: Subject-Driven Text-to-3D Generation
        14189, -- 2303.15433 Anti-DreamBooth: Protecting users from personalized text-to-image synt
        14363, -- 2304.00186 Subject-driven Text-to-Image Generation via Apprenticeship Learning
        14515, -- 2304.03411 InstantBooth: Personalized Text-to-Image Generation without Test-Time
        15239, -- 2305.03048 Personalize Segment Anything Model with One Shot
        15691, -- 2305.10701 Personalization as a Shortcut for Few-Shot Backdoor Attack against Tex
        16005, -- 2305.13873 Unsafe Diffusion: On the Generation of Unsafe Images and Hateful Memes
        16124, -- 2305.14720 BLIP-Diffusion: Pre-trained Subject Representation for Controllable Te
        16808, -- 2306.00983 StyleDrop: Text-to-Image Generation in Any Style
        18060, -- 2307.03108 DIAGNOSIS: Detecting Unauthorized Data Usages in Text-to-image Diffusi
        18134, -- 2307.04725 AnimateDiff: Animate Your Personalized Text-to-Image Diffusion Models
        18220, -- 2307.06949 HyperDreamBooth: HyperNetworks for Fast Personalization of Text-to-Ima
        19846, -- 2308.14256 FaceChain: A Playground for Human-centric Artificial Intelligence Gene
        19965, -- 2308.16512 MVDream: Multi-view Diffusion for 3D Generation
        20039, -- 2309.00952 Bridge Diffusion Model: bridge non-English language-native text-to-ima
        20088, -- 2309.01770 StyleAdapter: A Unified Stylized Image Generation Model
        20689, -- 2309.11497 FreeU: Free Lunch in Diffusion U-Net
        20924, -- 2309.14751 Text-image guided Diffusion Model for generating Deepfake celebrity in
        22566, -- 2310.16818 DreamCraft3D: Hierarchical 3D Generation with Bootstrapped Diffusion P
        22956, -- 2311.02343 Stable Diffusion Reference Only: Image Prompt and Blueprint Jointly Gu
        24072, -- 2312.00079 HiFi Tuner: High-Fidelity Subject-Driven Fine-Tuning for Diffusion Mod
        24290, -- 2312.02663 FaceStudio: Put Your Face Everywhere in Seconds
        25818, -- 2401.07519 InstantID: Zero-shot Identity-Preserving Generation in Seconds
        26266, -- 2401.13974 BootPIG: Bootstrapping Zero-shot Personalized Image Generation Capabil
        28055, -- 2402.17412 DiffuseKronA: A Parameter Efficient Fine-tuning Method for Personalize
        28291, -- 2403.01108 Face Swap via Diffusion Model
        28359, -- 2403.02084 ResAdapter: Domain Consistent Resolution Adapter for Diffusion Models
        30063, -- 2404.05256 StyleForge: Enhancing Text-to-Image Synthesis for Any Artistic Styles
        31637, -- 2405.14869 PuzzleAvatar: Assembling 3D Avatars from Personal Albums
        32514, -- 2406.05000 AttnDreamBooth: Towards Text-Aligned Personalized Text-to-Image Genera
        34252, -- 2407.05312 An Improved Method for Personalizing Diffusion Models
        34451, -- 2407.08019 Coherent and Multi-modality Image Inpainting via Latent Space Optimiza
        34505, -- 2407.08674 Still-Moving: Customized Video Generation without Customized Video Dat
        34788, -- 2407.12164 Subject-driven Text-to-Image Generation via Preference-based Reinforce
        37382, -- 2409.17920 Resolving Multi-Condition Confusion for Finetuning-Free Personalized I
        37984, -- 2410.04891 Low-Rank Continual Personalization of Diffusion Models
        38231, -- 2410.07763 HARIVO: Harnessing Text-to-Image Models for Video Generation
        38652, -- 2410.12928 DreamCraft3D++: Efficient Hierarchical 3D Generation with Multi-Plane
        41083, -- 2412.04465 UnZipLoRA: Separating Content and Style from a Single Image
        41253, -- 2412.06774 Visual Lexicon: Rich Image Features in Language Space
        45709, -- 2503.06568 Conceptrol: Concept Control of Zero-shot Personalized Image Generation
        46527, -- 2503.16944 HyperLoRA: Parameter-Efficient Adaptive Generation for Portrait Synthe
        47350, -- 2504.04722 TactileNet: Bridging the Accessibility Gap with AI-Generated Tactile G
        47985, -- 2504.15009 Insert Anything: Image Insertion via In-Context Editing in DiT
        49729, -- 2505.19415 MMIG-Bench: Towards Comprehensive and Explainable Evaluation of Multi-
        51738, -- 2507.05566 SingLoRA: Low Rank Adaptation Using a Single Matrix
        56857, -- 2603.18524 3DreamBooth: High-Fidelity 3D Subject-Driven Video Generation Model
        65398, -- 2511.03156 Finetuning-Free Personalization of Text to Image Generation via Hypern
        66679, -- 2510.09475 Few-shot multi-token DreamBooth with LoRa for style-consistent charact
        72662, -- 2505.20975 DreamBoothDPO: Improving Personalized Generation using Direct Preferen
        85261, -- 2604.03454 RDFace: A Benchmark Dataset for Rare Disease Facial Image Analysis und
        87201, -- 2505.18766 StyleGuard: Preventing Text-to-Image-Model-based Style Mimicry Attacks
        89449, -- 2410.03039 Leveraging Model Guidance to Extract Training Data from Personalized D
        90504, -- 2412.11638 IDProtector: An Adversarial Noise Encoder to Protect Against ID-Preser
        107175, -- 2601.07253 Universal Adversarial Purification with DDIM Metric Loss for Stable Di
        112538, -- 2311.13833 Lego: Learning to Disentangle and Invert Personalized Concepts Beyond
        112911, -- 2311.18815 IMMA: Immunizing text-to-image Models against Malicious Adaptation
        115619, -- 2405.01356 Improving Subject-Driven Image Synthesis with Subject-Agnostic Guidanc
        116117, -- 2404.11120 TiNO-Edit: Timestep and Noise Optimization for Robust Diffusion-Based
        116155, -- 2404.15081 Perturbing Attention Gives You More Bang for the Buck: Subtle Imaging
        116206, -- 2403.11162 CGI-DM: Digital Copyright Authentication for Diffusion Models via Cont
        116818, -- 2406.04542 M&M VTO: Multi-Garment Virtual Try-On and Editing
        120370, -- external Harnessing Global-Local Collaborative Adversarial Perturbation for Ant
        122935, -- 2609.38680 ReGain: Restoring Subject Fidelity in Personalization on Synthetic Ima
        131626  -- 2610.40453 PhysInsert: Physically Plausible Object Insertion with Geometric Prior
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
        53862, -- 2510.20512 EchoDistill: Bidirectional Concept Distillation for One-Step Diffusion
        53865, -- 2510.23605 Track, Inpaint, Resplat: Subject-driven 3D and 4D Generation with Prog
        53882, -- 2510.24657 Group Relative Attention Guidance for Image Editing
        53899, -- 2510.24448 Rethinking Visual Intelligence: Insights from Video Pretraining
        53958, -- 2510.26583 Emu3.5: Native Multimodal Models are World Learners
        54008, -- 2510.24078 Beyond Objects: Contextual Synthetic Data Generation for Fine-Grained
        54165, -- 2511.07499 Toward the Frontiers of Reliable Diffusion Sampling via Adversarial Si
        54243, -- 2511.10555 A Style is Worth One Code: Unlocking Code-to-Style Image Generation wi
        54272, -- 2511.15700 First Frame Is the Place to Go for Video Content Customization
        54403, -- 2511.21691 Canvas-to-Image: Compositional Image Generation with Multimodal Contro
        54448, -- 2511.20614 The Consistency Critic: Correcting Inconsistencies in Generated Images
        54460, -- 2511.17282 Where Culture Fades: Revealing the Cultural Gap in Text-to-Image Gener
        54463, -- 2511.22989 MultiBanana: A Challenging Benchmark for Multi-Reference Text-to-Image
        54480, -- 2512.01686 DreamingComics: A Story Visualization Pipeline via Subject and Layout
        54513, -- 2512.01989 PAI-Bench: A Comprehensive Benchmark For Physical AI
        54524, -- 2512.03013 In-Context Sync-LoRA for Portrait Video Editing
        54556, -- 2512.03979 BlurDM: A Blur Diffusion Model for Image Deblurring
        54587, -- 2512.05076 BulletTime: Decoupled Control of Time and Camera Pose for Video Genera
        54594, -- 2512.03683 GaussianBlender: Instant Stylization of 3D Gaussians with Disentangled
        54643, -- 2512.08294 OpenSubject: Leveraging Video-Derived Identity and Diversity Priors fo
        54658, -- 2512.07951 Preserving Source Video Realism: High-Fidelity Face Swapping for Cinem
        54686, -- 2512.09824 Composing Concepts from Images and Videos via Concept-prompt Binding
        54722, -- 2512.10955 Omni-Attribute: Open-vocabulary Attribute Encoder for Visual Concept P
        54727, -- 2512.04537 X-Humanoid: Robotize Human Videos to Generate Humanoid Videos at Scale
        54773, -- 2512.13421 RecTok: Reconstruction Distillation along Rectified Flow
        54781, -- 2512.13672 Directional Textual Inversion for Personalized Text-to-Image Generatio
        54795, -- 2512.12675 Scone: Bridging Composition and Distinction in Subject-Driven Image Ge
        54870, -- 2512.16625 DeContext as Defense: Safe Image Editing in Diffusion Transformers
        54943, -- 2512.19661 Over++: Generative Video Compositing for Layer Interaction Effects
        55034, -- 2512.22984 Reverse Personalization
        55036, -- 2512.22525 DreamOmni3: Scribble-based Editing and Generation
        55078, -- 2512.24146 Taming Preference Mode Collapse via Directional Decoupling Alignment i
        55108, -- 2512.22877 M-ErasureBench: A Comprehensive Multimodal Evaluation Benchmark for Co
        55121, -- 2601.03256 Muses: Designing, Composing, Generating Nonexistent Fantasy 3D Creatur
        55171, -- 2601.05124 Re-Align: Structured Reasoning-guided Alignment for In-Context Image G
        55323, -- 2601.10714 Alterbute: Editing Intrinsic Attributes of Objects in Images
        55336, -- 2601.08881 TAG-MoE: Task-Aware Gating for Unified Generative Mixture-of-Experts
        55652, -- 2601.22680 Visual Personalization Turing Test
        55680, -- 2602.01335 Beyond Pixels: Visual Metaphor Transfer via Schema-Driven Agentic Reas
        55741, -- 2602.03454 Contextualized Visual Personalization in Vision-Language Models
        55774, -- 2602.04575 Vibe AIGC: A New Paradigm for Content Generation via Agentic Orchestra
        55998, -- 2602.11144 GENIUS: Generative Fluid Intelligence Evaluation Suite
        56053, -- 2602.12280 Stroke of Surprise: Progressive Semantic Illusions in Vector Sketching
        56206, -- 2602.16968 DDiT: Dynamic Patch Scheduling for Efficient Diffusion Transformers
        56225, -- 2602.15727 Spanning the Visual Analogy Space with a Weight Basis of LoRAs
        56436, -- 2603.03281 CFG-Ctrl: Control-Based Classifier-Free Diffusion Guidance
        56488, -- 2603.02210 HiFi-Inpaint: Towards High-Fidelity Reference-Based Inpainting for Gen
        56567, -- 2603.07236 HY-WU (Part I): An Extensible Functional Neural Memory Framework and A
        56606, -- 2603.02816 BrandFusion: A Multi-Agent Framework for Seamless Brand Integration in
        56625, -- 2603.10256 ID-LoRA: Identity-Driven Audio-Video Personalization with In-Context L
        56653, -- 2603.11593 WeEdit: A Dataset, Benchmark and Glyph-Guided Framework for Text-centr
        56692, -- 2603.08258 WaDi: Weight Direction-aware Distillation for One-step Image Synthesis
        56734, -- 2603.15478 ViFeEdit: A Video-Free Tuner of Your Video Diffusion Transformer
        56763, -- 2603.12743 MoKus: Leveraging Cross-Modal Knowledge Transfer for Knowledge-Aware C
        56898, -- 2603.19708 WorldAgents: Can Foundation Image Models be Agents for 3D World Models
        56954, -- 2603.21884 Not All Layers Are Created Equal: Adaptive LoRA Ranks for Personalized
        56980, -- 2603.21937 MultiBind: A Benchmark for Attribute Misbinding in Multi-Subject Gener
        57028, -- 2603.24793 AVControl: Efficient Framework for Training Audio-Visual Controls
        57074, -- 2603.27862 ImagenWorld: Stress-Testing Image Generation Models with Explainable H
        57128, -- 2603.26174 CREval: An Automated Interpretable Evaluation for Creative Image Manip
        57134, -- 2603.27520 TokenDial: Continuous Attribute Control in Text-to-Video via Spatiotem
        57135, -- 2603.26357 MPDiT: Multi-Patch Global-to-Local Transformer Architecture For Effici
        57200, -- 2604.02088 FlowSlider: Training-Free Continuous Image Editing via Fidelity-Steeri
        57205, -- 2604.01929 Woosh: A Sound Effects Foundation Model
        57242, -- 2604.04911 SpatialEdit: Benchmarking Fine-Grained Image Spatial Editing
        57335, -- 2604.08364 MegaStyle: Constructing Diverse and Scalable Style Dataset via Consist
        57341, -- 2604.08302 DMax: Aggressive Parallel Decoding for dLLMs
        57366, -- 2604.08536 RewardFlow: Generate Images by Optimizing What You Reward
        57371, -- 2604.07427 Personalizing Text-to-Image Generation to Individual Taste
        57633, -- 2604.19254 ShadowPEFT: Shadow Network for Parameter-Efficient Fine-Tuning
        57793, -- 2604.24351 Diffusion Templates: A Unified Plugin Framework for Controllable Diffu
        57813, -- 2604.27505 Leveraging Verifier-Based Reinforcement Learning in Image Editing
        57827, -- 2604.24953 ViPO: Visual Preference Optimization at Scale
        58215, -- 2604.12575 StructDiff: A Structure-Preserving and Spatially Controllable Diffusio
        58360, -- 2604.08915 Large-Scale Universal Defect Generation: Foundation Models and Dataset
        58507, -- 2604.04487 Training-Free Image Editing with Visual Context Integration and Concep
        58764, -- 2603.28493 ConceptWeaver: Weaving Disentangled Concepts with Flow
        58767, -- 2603.28367 Rethinking Structure Preservation in Text-Guided Image Editing with Vi
        58796, -- 2603.27637 OPRO: Orthogonal Panel-Relative Operators for Panel-Aware In-Context I
        58874, -- 2603.25441 Language-Free Generative Editing from One Visual Example
        58995, -- 2603.23010 Zero-Shot Personalization of Objects via Textual Inversion
        59059, -- 2603.21176 GIDE: Unlocking Diffusion LLMs for Precise Training-Free Image Editing
        59097, -- 2603.19862 IsoCLIP: Decomposing CLIP Projectors for Efficient Intra-modal Alignme
        59160, -- 2603.20304 Transferable Multi-Bit Watermarking Across Frozen Diffusion Models via
        59285, -- 2603.16566 VideoMatGen: PBR Materials through Joint Generative Modeling
        59457, -- 2603.12930 Rethinking VLMs for Image Forgery Detection and Localization
        59766, -- 2603.06873 PICS: Pairwise Image Compositing with Spatial Interactions
        60000, -- 2602.20839 Training-Free Multi-Concept Image Editing
        60057, -- 2602.23697 Towards Source-Aware Object Swapping with Initial Noise Perturbation
        60191, -- 2602.23732 A Difference-in-Difference Approach to Detecting AI-Generated Images
        60265, -- 2602.22197 Off-The-Shelf Image-to-Image Models Are All You Need To Defeat Image P
        60309, -- 2602.21402 FlowFixer: Towards Detail-Preserving Subject-Driven Generation
        60344, -- 2602.20721 CleanStyle: Plug-and-Play Style Conditioning Purification for Text-to-
        60390, -- 2602.19575 ConceptPrism: Concept Disentanglement in Personalized Diffusion Models
        60704, -- 2602.13028 Human-Aligned MLLM Judges for Fine-Grained Image Editing Evaluation: A
        60984, -- 2602.08615 Inspiration Seeds: Learning Non-Literal Visual Combinations for Genera
        61357, -- 2602.03220 PokeFusion Attention: Enhancing Reference-Free Style-Conditioned Gener
        61531, -- 2602.01306 DeCorStory: Gram-Schmidt Prompt Embedding Decorrelation for Consistent
        61779, -- 2601.22094 RefAny3D: 3D Asset-Referenced Diffusion Models for Image Generation
        62372, -- 2601.12808 Joint Source-Channel-Generation Coding: From Distortion-oriented Recon
        62596, -- 2601.07833 Tuning-free Visual Effect Transfer across Videos
        62672, -- 2601.06965 Unified Personalized Understanding, Generating and Editing
        62698, -- 2601.06605 Sissi: Zero-shot Style-guided Image Synthesis via Semantic-style Integ
        62770, -- 2601.05127 LooseRoPE: Content-aware Attention Manipulation for Semantic Harmoniza
        62942, -- 2601.02987 LAMS-Edit: Latent and Attention Mixing with Schedulers for Improved Co
        63000, -- 2601.02098 InpaintHuman: Reconstructing Occluded Humans with Multi-Scale UV Mappi
        63109, -- 2601.00590 SafeMo: Linguistically Grounded Unlearning for Trustworthy Text-to-Mot
        63150, -- 2601.00090 It's Never Too Late: Noise Optimization for Collapse Recovery in Train
        63214, -- 2512.23592 Same or Not? Enhancing Visual Perception in Vision-Language Models
        63219, -- 2512.23537 AnyMS: Bottom-up Attention Decoupling for Layout-guided and Training-f
        63430, -- 2512.19479 Emotion-Director: Bridging Affective Shortcut in Emotion-Oriented Imag
        63757, -- 2512.12375 V-Warper: Appearance-Consistent Video Diffusion Personalization via Va
        63764, -- 2512.12220 ProImage-Bench: Rubric-Based Evaluation for Professional Image Generat
        63772, -- 2512.12193 SMRABooth: Subject and Motion Representation Alignment for Customized
        63783, -- 2512.11763 Reducing Domain Gap with Diffusion-Based Domain Adaptation for Cell Co
        63938, -- 2512.08477 ContextDrag: Precise Drag-Based Image Editing via Context-Preserving T
        63987, -- 2512.07348 MICo-150K: A Comprehensive Dataset Advancing Multi-Image Composition
        64154, -- 2512.03981 DirectDrag: High-Fidelity, Mask-Free, Prompt-Free Drag-based Image Edi
        64156, -- 2512.03964 Training for Identity, Inference for Controllability: A Unified Approa
        64256, -- 2512.01895 StyleYourSmile: Cross-Domain Face Retargeting Without Paired Multi-Sty
        64308, -- 2512.01236 PSR: Scaling Multi-Subject Personalized Image Generation with Pairwise
        64481, -- 2511.21216 AuthenLoRA: Entangling Stylization with Imperceptible Watermarks for C
        64498, -- 2511.20986 Inversion-Free Style Transfer with Dual Rectified Flows
        64562, -- 2511.19965 HiCoGen: Hierarchical Compositional Text-to-Image Generation in Diffus
        64680, -- 2511.18333 ConsistCompose: Unified Multimodal Layout Control for Image Compositio
        64688, -- 2511.18281 Uni-DAD: Unified Distillation and Adaptation of Diffusion Models for F
        64705, -- 2511.17979 FeRA: Frequency-Energy Constrained Routing for Effective Diffusion Ada
        64766, -- 2511.16666 SceneDesigner: Controllable Multi-Object Image Generation with 9-DoF P
        64830, -- 2511.15258 SplitFlux: Learning to Decouple Content and Style from a Single Image
        64833, -- 2511.15197 Insert In Style: A Zero-Shot Generative Framework for Harmonious Cross
        64938, -- 2511.13002 Infinite-Story: A Training-Free Consistent Text-to-Image Generation
        65299, -- 2511.05219 FreeControl: Efficient, Training-Free Structural Control via One-Step
        65541, -- 2511.00511 ID-Composer: Multi-Subject Video Synthesis with Hierarchical Identity
        65760, -- 2510.24037 Kernelized Sparse Fine-Tuning with Bi-level Parameter Competition for
        65766, -- 2510.23956 Neural USD: An object-centric framework for iterative editing and cont
        65791, -- 2510.23515 FreeFuse: Multi-Subject LoRA Fusion via Auto Masking at Test Time
        65907, -- 2510.21461 Enhancing Video Inpainting with Aligned Frame Interval Guidance
        82847, -- 2605.05204 D-OPSD: On-Policy Self-Distillation for Continuously Tuning Step-Disti
        83005, -- 2604.23789 MuSS: A Large-Scale Dataset and Cinematic Narrative Benchmark for Mult
        83317, -- 2605.10302 Follow the Mean: Reference-Guided Flow Matching
        83767, -- 2605.08129 Towards Customized Multimodal Role-Play
        83769, -- 2605.25191 Injecting Image Guidance into Text-Conditioned Diffusion Models at Inf
        83818, -- 2605.26111 Squeezing Capacity from Multimodal Large Language Models for Subject-d
        83822, -- 2605.26632 RT-Lynx: Putting the GEMM Sparsity In a Right Way for Diffusion Models
        83917, -- 2605.25378 CollectionLoRA: Collecting 50 Effects in 1 LoRA via Multi-Teacher On-P
        84162, -- 2511.11944 From Events to Clarity: The Event-Guided Diffusion Framework for Dehaz
        84259, -- 2511.21136 Efficient Training for Human Video Generation with Entropy-Guided Prio
        84275, -- 2511.22287 Match-and-Fuse: Consistent Generation from Unstructured Image Sets
        84296, -- 2512.00677 Dynamic-eDiTor: Training-Free Text-Driven 4D Scene Editing with Multim
        84340, -- 2512.04485 Not All Birds Look The Same: Identity-Preserving Generation For Birds
        84357, -- 2512.06662 Personalized Image Descriptions from Attention Sequences
        84381, -- 2512.10943 AlcheMinT: Fine-grained Temporal Control for Multi-Reference Consisten
        84402, -- 2512.14236 Elastic3D: Controllable Stereo Video Conversion with Guided Latent Dec
        84405, -- 2512.15347 Expand and Prune: Maximizing Trajectory Diversity for Effective GRPO i
        84418, -- 2512.17320 EMMA: Concept Erasure Benchmark with Comprehensive Semantic Metrics an
        84422, -- 2512.18312 MatE: Material Extraction from Single-Image via Geometric Prior
        84485, -- 2601.14602 3D Space as a Scratchpad for Editable Text-to-Image Generation
        84494, -- 2601.20511 Say Cheese! Detail-Preserving Portrait Collection Generation via Natur
        84534, -- 2602.19019 TokenTrace: Multi-Concept Attribution through Watermarked Token Recove
        84557, -- 2602.19565 DICArt: Advancing Category-level Articulated Object Pose Estimation in
        84563, -- 2602.19679 TeHOR: Text-Guided 3D Human and Object Reconstruction with Textures
        84611, -- 2602.21977 When LoRA Betrays: Backdooring Text-to-Image Models by Masquerading as
        84618, -- 2602.22150 CoLoGen: Progressive Learning of Concept-Localization Duality for Unif
        84778, -- 2603.06289 FlowMotion: Training-Free Flow Guidance for Video Motion Transfer
        84831, -- 2603.09771 Ego: Embedding-Guided Personalization of Vision-Language Models
        84865, -- 2603.11795 Intrinsic Concept Extraction Based on Compositional Interpretability
        84881, -- 2603.12766 Catalyst4D: High-Fidelity 3D-to-4D Scene Editing via Dynamic Propagati
        84907, -- 2603.14209 ChArtist: Generating Pictorial Charts with Unified Spatial and Subject
        84932, -- 2603.16100 Reevaluating the Intra-Modal Misalignment Hypothesis in CLIP
        84951, -- 2603.17531 Rel-Zero: Harnessing Patch-Pair Invariance for Robust Zero-Watermarkin
        84964, -- 2603.18093 One-to-More: High-Fidelity Training-Free Anomaly Generation with Atten
        85003, -- 2603.20470 DiffGraph: An Automated Agent-driven Model Merging Framework for In-th
        85011, -- 2603.20755 Memory-Efficient Fine-Tuning Diffusion Transformers via Dynamic Patch
        85044, -- 2603.22091 P-Flow: Prompting Visual Effects Generation
        85056, -- 2603.22883 Group Editing: Edit Multiple Images in One Go
        85093, -- 2603.24570 Anti-I2V: Safeguarding your Photos from Malicious Image-to-video Gener
        85112, -- 2603.25188 AnyID: Ultra-Fidelity Universal Identity-Preserving Video Generation f
        85188, -- 2603.28152 ObjectMorpher: 3D-Aware Image Editing via Deformable 3DGS
        85223, -- 2604.00849 Disentangling to Re-couple: Resolving the Similarity-Controllability P
        85283, -- 2604.05039 ID-Sim: An Identity-Focused Similarity Metric
        85285, -- 2604.05183 OrthoFuse: Training-free Riemannian Fusion of Orthogonal Style-Concept
        85305, -- 2604.07795 Image-Guided Geometric Stylization of 3D Meshes
        85340, -- 2604.10032 Closed-Form Concept Erasure via Double Projections
        85393, -- 2604.15829 Beyond Text Prompts: Precise Concept Erasure through Text-Image Collab
        85408, -- 2604.17195 DreamShot: Personalized Storyboard Synthesis with Video Diffusion Prio
        85532, -- 2605.08589 S2FT: Parameter-Efficient Fine-Tuning in Sparse Spectrum Domain
        93374, -- 2603.02541 ForestPersons: A Large-Scale Dataset for Under-Canopy Missing Person D
        93463, -- 2602.07095 WorldEdit: Towards Open-World Image Editing with a Knowledge-Informed
        94571, -- 2604.12286 LiveMoments: Reselected Key Photo Restoration in Live Photos via Refer
        98317, -- 2606.12883 The Hidden Power of Scaling Factor in LoRA Optimization
        98482, -- 2606.15158 RefGC-SR^2: Reference-guided Generated Content Super-Resolution and Re
        98540, -- 2606.20506 FreeStyle: Free Control of Style-Content Dual-Reference Generation fro
        98586, -- 2606.20556 Thinking in Boxes: 3D Editing in Real Images Made Easy
        98754, -- 2606.22875 FedOT: Ownership Verification and Leakage Tracing via Watermarks for F
        98755, -- 2606.24548 Are Text-to-Image Models Inductivist Turkeys? A Counterfactual Benchma
        98846, -- 2606.27377 DanceOPD: On-Policy Generative Field Distillation
        98884, -- 2601.17756 MV-S2V: Multi-View Subject-Consistent Video Generation
        99033, -- 2606.32033 SpheRoPE: Zero-Shot Optimization-Free 360 Panorama Generation with Sph
        99115, -- 2605.31266 Envisioning Beyond the Few: Disentangled Semantics and Primitives for
        99264, -- 2602.03410 UnHype: CLIP-Guided Hypernetworks for Dynamic LoRA Unlearning
        99533, -- 2605.15803 Embedding-perturbed Exploration Preference Optimization for Flow Model
        99736, -- 2606.10617 SSR-Merge: Subspace Signal Routing for Training-Free LoRA Merging in D
        99763, -- 2512.20014 Bring My Cup! Personalizing Vision-Language-Action Models with Visual
        99962, -- 2603.07615 Compression as Adaptation: Implicit Visual Representation with Diffusi
        100430, -- 2604.18804 Geometric Decoupling: Diagnosing the Structural Instability of Latent
        100526, -- 2606.09250 LiteVSR: Lightweight Adaptation of Frozen Diffusion Transformers for V
        100823, -- 2605.29716 NaRA: Noise-Aware LoRA for Parameter-Efficient Fine-Tuning of Diffusio
        100863, -- 2606.10902 Pose-ICL: 3D-Aware In-Context Learning for Pose-Controllable Subject C
        101368, -- 2601.08379 MMD Guidance: Training-Free Distribution Adaptation for Diffusion Mode
        102185, -- 2603.06981 Diffusion Controller: Framework, Algorithms and Parameterization
        102414, -- 2605.29809 Cert-LAS: Toward Certified Model Ownership Verification for Text-to-Im
        102461, -- 2605.23410 What Linear Probes Miss: Multi-View Probing for Weight-Space Learning
        103447, -- 2604.07422 Multimodal Large Language Models for Multi-Subject In-Context Image Ge
        103906, -- 2606.27371 Don't Settle at the Mode! Mitigating Diversity Collapse in Pretrained
        103947, -- 2607.11885 Latent-Identity Tuning in Text-to-Image Personalization Models
        104000, -- 2607.05382 Search Beyond What Can Be Taught: Evolving the Knowledge Boundary in A
        104015, -- 2607.12752 Hallo4D: Multi-Modal Hallucination Mitigation for Consistent Spatio-Te
        104395, -- 2607.18217 HOMIE: Human-object Centric Video Personalization via Multimodal Intel
        104829, -- 2602.08198 PEGAsus: 3D Personalization of Geometry and Appearance
        105980, -- 2606.03792 Training-Free Multi-Concept LoRA Composition with Prompt-Aware Weighti
        106067, -- 2608.00440 Poplar: A Scalable Pipeline for Human-Centric Image Dataset Synthesis
        106789, -- 2511.13297 CorrectAD: A Self-Correcting Agentic System to Improve End-to-end Plan
        106793, -- 2511.11060 CareCom: Generative Image Composition with Calibrated Reference Featur
        106981, -- 2512.03335 Step-by-step Layered Design Generation
        107225, -- 2512.10433 Targeted Data Protection for Diffusion Model by Matching Training Traj
        107510, -- 2511.13713 Free-Form Scene Editor: Enabling Multi-Round Object Manipulation Like
        107534, -- 2602.18282 DEIG: Detail-Enhanced Instance Generation with Fine-Grained Semantic C
        107584, -- 2511.08252 Melodia: Training-Free Music Editing Guided by Attention Probing in Di
        107742, -- 2603.14220 FIND: A Simple Yet Effective Baseline for Diffusion-Generated Image De
        107919, -- 2512.23519 IdentityStory: Taming Your Identity-Preserving Generator for Human-Cen
        108253, -- 2512.15818 Unveiling the Attribute Misbinding Threat in Identity-Preserving Model
        108289, -- 2511.12935 PFAvatar: Pose-Fusion 3D Personalized Avatar Reconstruction from Real-
        108318, -- 2601.01892 Forget Less by Learning from Parents Through Hierarchical Relationship
        109065, -- 2608.06751 Beyond Starry Night: Shortcut-Aware Control-State Planning for Artist-
        109396, -- 2608.16765 TRACE-Bench: Decomposing and Diagnosing Multi-Reference Image Generati
        113986, -- 2606.15867 CogCanvas: A Benchmark for Evaluating Multi-Subject Reference-Based Im
        114015, -- 2609.06758 Agentic Visual Generation: From Generative Models to Agentic Control
        117454, -- 2608.11546 Through Van Gogh’s Eyes: Global Style Transfer with Diffusion Model
        117562, -- 2605.16990 DreamEdit3D: Personalization of Multi-View Diffusion Models for 3D Edi
        118136, -- 2607.14595 MagicPrompt: Ultra-Lightweight Prompt Tuning for Video Generation
        118363, -- 2603.13547 NumColor: Precise Numeric Color Control in Text-to-Image Generation
        118422, -- 2603.08090 DSH-Bench: A Difficulty- and Scenario-Aware Benchmark with Hierarchica
        118440, -- 2607.06440 PIPBench: A Profile-Inclusive Framework for Personalized Image Generat
        118506, -- 2607.26647 Anchoring and Steering Diffusion: Enhancing the Faithfulness of Text-t
        118550, -- 2607.14945 Introspective Attention Modulation for Safe Text-to-Image Generation
        118551, -- 2511.21122 Which Layer Causes Distribution Deviation? Entropy-Guided Adaptive Pru
        118578, -- 2603.18466 Recolour What Matters: Region-Aware Colour Editing via Token-Level Dif
        118590, -- 2607.04677 AnyStyle: A Single LoRA is Sufficient for Image-Guided Style Transfer
        118623, -- 2606.31683 Histogram-constrained Image Generation
        118632, -- 2607.15845 Knowledge-Centric Agents for Workflow Generation in ComfyUI
        118676, -- 2606.28845 Personalizing MLLMs via Reinforced Multimodal Reference Game
        118864, -- 2606.30528 μFlow: Leveraging Average Images for Improving Generalisation of Deepf
        118936, -- 2606.29880 IREU: Identity-Related Encoder-Only Unlearning for Customized Portrait
        119192, -- 2606.20110 FrozenDrive: Zero-Shot Text-Guided Driving Scene Generation and Data A
        119558, -- 2607.06918 LoCA: Spatially-Aware Low-Rank Convolutional Adaptation of Vision Foun
        120758, -- 2602.00267 PLACID: Identity-Preserving Multi-Object Compositing via Video Diffusi
        121184, -- 2602.21273 StoryTailor:A Zero-Shot Pipeline for Action-Rich Multi-Subject Visual
        121276, -- 2605.17294 HierEdit: Region-Aware Hierarchical Diffusion for Efficient High-Resol
        122264, -- 2609.35530 AutoRef: Harness Optimization for Agentic Multi-Reference Image Genera
        122582, -- 2610.00737 Personalized Image Generation with Reasoning and Reflection
        122853, -- 2609.39096 DeCoPrune: Efficient KV-Cache Pruning for Autoregressive Video Diffusi
        122904, -- 2610.07250 Internalizing Agent Experience into Diffusion Model Weights via On-Pol
        122948, -- 2610.12230 From Prompting to Composing: A Spatial Canvas Interface for Poster Gen
        123408, -- 2604.01973 NearID: Identity Representation Learning via Near-identity Distractors
        124162, -- 2610.11067 Diffusion Meta-Prompting and Steering for Generalizable Foundation Mod
        124796, -- 2511.11051 NP-LoRA: Null Space Projection for Subject-Style LoRA Fusion
        124963, -- 2606.06120 Diff-CA: Separating Common and Salient Factors with Diffusion Models
        127570, -- 2609.33716 Revisiting Diffusion Fine-Tuning for Unsupervised Domain Adaptation
        130238, -- 2606.11670 ARGUS: Stacked Multi-View Identity Mosaic Injection for Subject-Preser
        130997, -- 2606.13768 CineOrchestra: Unified Entity-Centric Conditioning for Cinematic Video
        131065, -- 2601.04153 Diffusion-DRF: Free, Rich, and Differentiable Reward for Video Diffusi
        131556, -- 2610.35684 OmniShowcase: Omnidirectional Subject-Consistent Video Generation from
        131659, -- 2610.32978 SceneBloom: Agentic Indoor Environment Generation with Realistic and D
        131696, -- 2610.36545 FrameForge: Harnessing Priors of Video Foundation Models for Unified I
        131944, -- 2610.40119 SynthFaces: Balanced Large Scale Human Dataset
        131994  -- 2611.06856 LongBanana: An Expert-Verified Benchmark for Long-Context Multi-Refere
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
        9962, -- 2208.01618 An Image is Worth One Word: Personalizing Text-to-Image Generation usi
        11719, -- 2211.17115 Multiresolution Textual Inversion
        12939, -- 2302.03900 Zero-shot Generation of Coherent Storybook from Plain Text Story using
        13125, -- 2302.07865 Dataset Interfaces: Diagnosing Model Failures Using Controllable Count
        13835, -- 2303.09522 P+: Extended Textual Conditioning in Text-to-Image Generation
        14177, -- 2303.15247 Zero-Shot Composed Image Retrieval with Textual Inversion
        14363, -- 2304.00186 Subject-driven Text-to-Image Generation via Apprenticeship Learning
        14515, -- 2304.03411 InstantBooth: Personalized Text-to-Image Generation without Test-Time
        15691, -- 2305.10701 Personalization as a Shortcut for Few-Shot Backdoor Attack against Tex
        15955, -- 2305.13501 LaDI-VTON: Latent Diffusion Textual-Inversion Enhanced Virtual Try-On
        16005, -- 2305.13873 Unsafe Diffusion: On the Generation of Unsafe Images and Hateful Memes
        16592, -- 2305.18993 ConES: Concept Embedding Search for Parameter Efficient Tuning Large V
        16808, -- 2306.00983 StyleDrop: Text-to-Image Generation in Any Style
        17698, -- 2306.13078 Continuous Layout Editing of Single Images with Diffusion Models
        17924, -- 2306.17843 Magic123: One Image to High-Quality 3D Object Generation Using Both 2D
        18220, -- 2307.06949 HyperDreamBooth: HyperNetworks for Fast Personalization of Text-to-Ima
        18566, -- 2307.12560 Interpolating between Images with Diffusion Models
        20007, -- 2309.00248 DiffuGen: Adaptable Approach for Generating Labeled Image Datasets usi
        20039, -- 2309.00952 Bridge Diffusion Model: bridge non-English language-native text-to-ima
        20443, -- 2309.07986 Viewpoint Textual Inversion: Discovering Scene Representations and 3D
        21877, -- 2310.08368 Mapping Memes to Words for Multimodal Hateful Meme Classification
        23780, -- 2311.15477 DreamCreature: Crafting Photorealistic Virtual Creatures from Imaginat
        24072, -- 2312.00079 HiFi Tuner: High-Fidelity Subject-Driven Fine-Tuning for Diffusion Mod
        24290, -- 2312.02663 FaceStudio: Put Your Face Everywhere in Seconds
        24435, -- 2312.04433 DreamVideo: Composing Your Dream Videos with Customized Subject and Mo
        24786, -- 2312.09008 Style Injection in Diffusion: A Training-free Approach for Adapting La
        25203, -- 2312.15905 Cross Initialization for Personalized Text-to-Image Generation
        25818, -- 2401.07519 InstantID: Zero-shot Identity-Preserving Generation in Seconds
        26378, -- 2401.15636 FreeStyle: Free Lunch for Text-guided Style Transfer using Diffusion M
        27325, -- 2402.09368 Magic-Me: Identity-Specific Video Customized Diffusion
        27743, -- 2402.13763 Music Style Transfer with Time-Varying Inversion of Diffusion Models
        28318, -- 2403.01422 MovieLLM: Enhancing Long Video Understanding with AI-Generated Movies
        29302, -- 2403.14828 Multimodal-Conditioned Latent Diffusion Models for Fashion Image Editi
        31071, -- 2405.02951 iSEARLE: Improving Textual Inversion for Zero-Shot Composed Image Retr
        32514, -- 2406.05000 AttnDreamBooth: Towards Text-Aligned Personalized Text-to-Image Genera
        34252, -- 2407.05312 An Improved Method for Personalizing Diffusion Models
        34820, -- 2407.12563 Audio Conditioning for Music Generation via Discrete Bottleneck Featur
        34868, -- 2407.12939 GenRC: Generative 3D Room Completion from Sparse Image Collections
        35429, -- 2408.00458 Reenact Anything: Semantic Video Motion Transfer Using Motion-Textual
        35687, -- 2408.04785 BRAT: Bonus oRthogonAl Token for Architecture Agnostic Textual Inversi
        36250, -- 2408.14584 DIAGen: Diverse Image Augmentation with Generative Models
        38614, -- 2410.12526 Shaping a Stabilized Video by Mitigating Unintended Changes for Concep
        40153, -- 2411.12197 MTFusion: Reconstructing Any 3D Object from Single Image Using Multi-w
        40969, -- 2412.03297 Composed Image Retrieval for Training-Free Domain Conversion
        46365, -- 2503.14868 Efficient Personalization of Quantized Diffusion Model without Backpro
        47919, -- 2504.14011 Fashion-RAG: Multimodal Fashion Image Editing via Retrieval-Augmented
        49677, -- 2505.19063 Training-free Stylized Text-to-Image Generation with Fast Inference
        54781, -- 2512.13672 Directional Textual Inversion for Personalized Text-to-Image Generatio
        58730, -- 2603.29239 Diffusion Mental Averages
        58995, -- 2603.23010 Zero-Shot Personalization of Objects via Textual Inversion
        63000, -- 2601.02098 InpaintHuman: Reconstructing Occluded Humans with Multi-Scale UV Mappi
        74197, -- 2503.06984 Synchronized Video-to-Audio Generation via Mel Quantization-Continuum
        87201, -- 2505.18766 StyleGuard: Preventing Text-to-Image-Model-based Style Mimicry Attacks
        87575, -- 2503.17226 DDB: Diffusion Driven Balancing to Address Spurious Correlations
        88035, -- 2502.19697 Prompt-driven Transferable Adversarial Attack on Person Re-Identificat
        88356, -- 2507.10578 When and Where do Data Poisons Attack Textual Inversion?
        112538, -- 2311.13833 Lego: Learning to Disentangle and Invert Personalized Concepts Beyond
        112911, -- 2311.18815 IMMA: Immunizing text-to-image Models against Malicious Adaptation
        113503, -- 2312.02192 Diverse Text-to-3D Synthesis with Augmented Text Embedding
        115352, -- 2405.20607 Textual Inversion and Self-supervised Refinement for Radiology Report
        116117, -- 2404.11120 TiNO-Edit: Timestep and Noise Optimization for Robust Diffusion-Based
        116540, -- external Cross Initialization for Face Personalization of Text-to-Image Models
        117562, -- 2605.16990 DreamEdit3D: Personalization of Multi-View Diffusion Models for 3D Edi
        118399, -- 2607.23492 To Erase, or Not to Erase: Robust Training-Free Concept Erasure with P
        118687, -- 2607.02284 FlowCIR: Semantic Transport via Flow Matching for Zero-Shot Composed I
        120287, -- 2506.10182 Improving Personalized Search with Regularized Low-Rank Parameter Upda
        120631, -- external Generative Zero-Shot Composed Image Retrieval
        121857  -- external Beyond Explicit Language: Plug-and-Play Visual-to-Linguistic Modeling
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
        7607, -- 2112.13592 Multimodal Image Synthesis and Editing: The Generative AI Era
        8531, -- 2204.00598 Socratic Models: Composing Zero-Shot Multimodal Reasoning with Languag
        8591, -- 2204.02849 KNN-Diffusion: Image Generation via Large-Scale Retrieval
        10140, -- 2208.12242 DreamBooth: Fine Tuning Text-to-Image Diffusion Models for Subject-Dri
        10409, -- 2209.12330 Personalizing Text-to-Image Generation via Aesthetic Gradients
        10866, -- 2210.09276 Imagic: Text-Based Real Image Editing with Diffusion Models
        10871, -- 2210.09477 UniTune: Text-Driven Image Editing by Fine Tuning a Diffusion Model on
        11115, -- 2210.16056 MagicMix: Semantic Mixing with Diffusion Models
        11188, -- 2211.01324 eDiff-I: Text-to-Image Diffusion Models with an Ensemble of Expert Den
        11341, -- 2211.07600 Latent-NeRF for Shape-Guided Generation of 3D Shapes and Textures
        11348, -- 2211.07793 Extreme Generative Image Compression by Learning Text Embedding from D
        11417, -- 2211.09794 Null-text Inversion for Editing Real Images using Guided Diffusion Mod
        11418, -- 2211.09800 InstructPix2Pix: Learning to Follow Image Editing Instructions
        11457, -- 2211.10950 Synthesizing Coherent Story with Auto-Regressive Latent Diffusion Mode
        11504, -- 2211.11743 SinFusion: Training Diffusion Models on a Single Image or Video
        11529, -- 2211.12446 EDICT: Exact Diffusion Inversion via Coupled Transformations
        11540, -- 2211.12572 Plug-and-Play Diffusion Features for Text-Driven Image-to-Image Transl
        11546, -- 2211.12737 RoentGen: Vision-Language Foundation Model for Chest X-ray Generation
        11576, -- 2211.13203 Inversion-Based Style Transfer with Diffusion Models
        11580, -- 2211.13227 Paint by Example: Exemplar-based Image Editing with Diffusion Models
        11621, -- 2211.14305 SpaText: Spatio-Textual Representation for Controllable Image Generati
        11698, -- 2211.16374 DATID-3D: Diversity-Preserved Domain Adaptation Using Text-to-Image Di
        11701, -- 2211.16431 NeuralLift-360: Lifting An In-the-wild 2D Photo to A 3D Object with 36
        11707, -- 2211.16582 SinDDM: A Single Image Denoising Diffusion Model
        11728, -- 2211.17256 CLIPascene: Scene Sketching with Different Types and Levels of Abstrac
        11734, -- 2212.00210 Shape-Guided Diffusion with Inside-Outside Attention
        11837, -- 2212.03267 NeRDi: Single-View NeRF Synthesis with Language-Guided Diffusion as Ge
        11874, -- 2212.04488 Multi-Concept Customization of Text-to-Image Diffusion
        11875, -- 2212.04489 SINE: SINgle Image Editing with Text-to-Image Diffusion Models
        12180, -- 2212.10957 TruFor: Leveraging all-round clues for trustworthy image forgery detec
        12189, -- 2212.11565 Tune-A-Video: One-Shot Tuning of Image Diffusion Models for Text-to-Vi
        12248, -- 2212.14306 Zero-Shot Object Segmentation through Concept Distillation from Genera
        12259, -- 2212.14704 Dream3D: Zero-Shot Text-to-3D Synthesis Using 3D Shape Prior and Text-
        12278, -- 2301.00704 Muse: Text-To-Image Generation via Masked Generative Transformers
        12433, -- 2301.07485 Image Embedding for Denoising Generative Models
        12485, -- 2301.09515 StyleGAN-T: Unlocking the Power of GANs for Fast Large-Scale Text-to-I
        12650, -- 2301.12661 Make-An-Audio: Text-To-Audio Generation with Prompt-Enhanced Diffusion
        12722, -- 2301.13826 Attend-and-Excite: Attention-Based Semantic Guidance for Text-to-Image
        12819, -- 2302.01721 TEXTure: Text-Guided Texturing of 3D Shapes
        12892, -- 2302.03084 Pic2Word: Mapping Pictures to Words for Zero-shot Composed Image Retri
        12926, -- 2302.03668 Hard Prompts Made Easy: Gradient-Based Discrete Optimization for Promp
        12976, -- 2302.04578 Adversarial Example Does Good: Preventing Painting Imitation from Diff
        13021, -- 2302.05496 MaskSketch: Unpaired Structure-guided Masked Image Generation
        13023, -- 2302.05543 Adding Conditional Control to Text-to-Image Diffusion Models
        13082, -- 2302.06826 DiffFashion: Reference-based Fashion Design with Structure-aware Trans
        13129, -- 2302.07944 Effective Data Augmentation With Diffusion Models
        13203, -- 2302.09778 Composer: Creative and Controllable Image Synthesis with Composable Co
        13228, -- 2302.10663 RealFusion: 360° Reconstruction of Any Object from a Single Image
        13229, -- 2302.10688 On Calibrating Diffusion Probabilistic Models
        13234, -- 2302.10893 Fair Diffusion: Instructing Text-to-Image Generation Models on Fairnes
        13281, -- 2302.12192 Aligning Text-to-Image Models using Human Feedback
        13283, -- 2302.12228 Encoder-based Domain Tuning for Fast Personalization of Text-to-Image
        13314, -- 2302.12948 Agile Modeling: From Concept to Classifier in Minutes
        13320, -- 2302.13153 Directed Diffusion: Direct Control of Object Placement through Attenti
        13336, -- 2302.13848 ELITE: Encoding Visual Concepts into Textual Embeddings for Customized
        13467, -- 2303.01818 Word-As-Image for Semantic Typography
        13578, -- 2303.04761 Video-P2P: Video Editing with Cross-attention Control
        13595, -- 2303.05072 Identification of Systematic Errors of Image Classifiers on Rare Subgr
        13599, -- 2303.05125 Cones: Concept Neurons in Diffusion Models for Customized Generation
        13719, -- 2303.07345 Erasing Concepts from Diffusion Models
        13749, -- 2303.07909 Text-to-image Diffusion Models in Generative AI: A Survey
        13751, -- 2303.07937 Let 2D Diffusion Model Know 3D-Consistency for Robust Text-to-3D Gener
        13752, -- 2303.07945 Edit-A-Video: Single Video Editing with Object-Aware Consistency
        13759, -- 2303.08084 Editing Implicit Assumptions in Text-to-Image Diffusion Models
        13869, -- 2303.10073 DialogPaint: A Dialog-based Image Editing Model
        13873, -- 2303.10137 A Recipe for Watermarking Diffusion Models
        13894, -- 2303.10585 Label Name is Mantra: Unifying Point Cloud Segmentation across Heterog
        13914, -- 2303.11073 Discovering Interpretable Directions in the Semantic Latent Space of D
        13928, -- 2303.11305 SVDiff: Compact Parameter Space for Diffusion Fine-Tuning
        13929, -- 2303.11306 Localizing Object-level Shape Variations with Text-to-Image Diffusion
        13933, -- 2303.11328 Zero-1-to-3: Zero-shot One Image to 3D Object
        14011, -- 2303.12538 Affordance Diffusion: Synthesizing Hand-Object Interactions
        14044, -- 2303.13126 MagicFusion: Boosting Text-to-Image Generation Performance by Fusing D
        14067, -- 2303.13495 ReVersion: Diffusion-Based Relation Inversion from Images
        14071, -- 2303.13508 DreamBooth3D: Subject-Driven Text-to-3D Generation
        14074, -- 2303.13516 Ablating Concepts in Text-to-Image Diffusion Models
        14078, -- 2303.13703 End-to-End Diffusion Latent Optimization Improves Classifier Guidance
        14189, -- 2303.15433 Anti-DreamBooth: Protecting users from personalized text-to-image synt
        14190, -- 2303.15435 The Stable Signature: Rooting Watermarks in Latent Diffusion Models
        14202, -- 2303.15649 StyleDiffusion: Prompt-Embedding Inversion for Text-Based Editing
        14289, -- 2303.17155 Discriminative Class Tokens for Text-to-Image Diffusion Models
        14392, -- 2304.00916 DreamAvatar: Text-and-Shape Guided 3D Human Avatar Generation via Diff
        14442, -- 2304.01816 Toward Verifiable and Reproducible Human Evaluation for Text-to-Image
        14443, -- 2304.01830 Learning to Name Classes for Vision and Language Models
        14603, -- 2304.04968 Re-imagine the Negative Prompt Algorithm: Transform 2D Diffusion into
        14684, -- 2304.06720 Expressive Text-to-Image Generation with Rich Text
        14760, -- 2304.08818 Align your Latents: High-Resolution Video Synthesis with Latent Diffus
        14831, -- 2304.10253 Image retrieval outperforms diffusion models on data augmentation
        15153, -- 2305.01644 Key-Locked Rank One Editing for Text-to-Image Personalization
        15239, -- 2305.03048 Personalize Segment Anything Model with One Shot
        15257, -- 2305.03374 DisenBooth: Identity-Preserving Disentangled Tuning for Subject-Driven
        15316, -- 2305.04441 Prompt Tuning Inversion for Text-Driven Image Editing Using Diffusion
        15569, -- 2305.08694 A Reproducible Extraction of Training Images from Diffusion Models
        15579, -- 2305.08850 Make-A-Protagonist: Generic Video Editing with An Ensemble of Experts
        15672, -- 2305.10431 FastComposer: Tuning-Free Multi-Subject Image Generation with Localize
        15708, -- 2305.10855 TextDiffuser: Diffusion Models as Text Painters
        15722, -- 2305.11080 Inspecting the Geographical Representativeness of Images from Text-to-
        15872, -- 2305.12683 Mist: Towards Improved Adversarial Examples for Diffusion Models
        15905, -- 2305.13050 AudioToken: Adaptation of Text-Conditioned Diffusion Models for Audio-
        15910, -- 2305.13077 ControlVideo: Training-free Controllable Text-to-Video Generation
        15939, -- 2305.13301 Training Diffusion Models with Reinforcement Learning
        15963, -- 2305.13579 Enhancing Detail Preservation for Customized Text-to-Image Generation:
        16002, -- 2305.13840 Control-A-Video: Controllable Text-to-Video Diffusion Models with Moti
        16124, -- 2305.14720 BLIP-Diffusion: Pre-trained Subject Representation for Controllable Te
        16232, -- 2305.15296 MultiFusion: Fusing Pre-Trained Models for Multi-Lingual, Multi-Modal
        16246, -- 2305.15391 A Neural Space-Time Representation for Text-to-Image Personalization
        16258, -- 2305.15581 Unsupervised Semantic Correspondence Using Stable Diffusion
        16275, -- 2305.15779 Custom-Edit: Text-Guided Image Editing with Customized Diffusion Model
        16311, -- 2305.16225 ProSpect: Prompt Spectrum for Attribute-Aware Personalization of Diffu
        16320, -- 2305.16311 Break-A-Scene: Extracting Multiple Concepts from a Single Image
        16363, -- 2305.16807 Negative-prompt Inversion: Fast Image Inversion for Editing with Text-
        16410, -- 2305.17235 COMCAT: Towards Efficient Compression and Customization of Attention-B
        16485, -- 2305.18203 Concept Decomposition for Visual Exploration and Inspiration
        16490, -- 2305.18247 TaleCrafter: Interactive Story Visualization with Multiple Characters
        16493, -- 2305.18259 GlyphControl: Glyph Conditional Control for Visual Text Generation
        16494, -- 2305.18264 Gen-L-Video: Multi-Text to Long Video Generation via Temporal Co-Denoi
        16498, -- 2305.18286 Photoswap: Personalized Subject Swapping in Images
        16500, -- 2305.18292 Mix-of-Show: Decentralized Low-Rank Adaptation for Multi-Concept Custo
        16522, -- 2305.18425 Efficient Storage of Fine-Tuned Models via Low-Rank Approximation of W
        16551, -- 2305.18676 LayerDiffusion: Layered Controlled Image Editing with Diffusion Models
        16561, -- 2305.18729 Real-World Image Variation by Aligning Diffusion Inversion Chain
        16621, -- 2305.19327 Cones 2: Customizable Image Synthesis with Multiple Subjects
        16720, -- 2306.00219 Diffusion Brush: A Latent Diffusion Model-based Editing Tool for AI-ge
        16790, -- 2306.00926 Inserting Anybody in Diffusion Models via Celeb Basis
        16795, -- 2306.00950 Differential Diffusion: Giving Each Pixel Its Strength
        16799, -- 2306.00966 The Hidden Language of Diffusion Models
        16801, -- 2306.00971 ViCo: Plug-and-play Visual Condition for Personalized Text-to-image Ge
        16810, -- 2306.00986 Diffusion Self-Guidance for Controllable Image Generation
        16893, -- 2306.01872 Probabilistic Adaptation of Text-to-Video Models
        16922, -- 2306.02236 Detector Guidance for Multi-Object Text-to-Image Generation
        16985, -- 2306.03038 HeadSculpt: Crafting 3D Head Avatars with Text
        17120, -- 2306.04695 ConceptBed: Evaluating Concept Learning Abilities of Text-to-Image Dif
        17125, -- 2306.04744 WOUAF: Weight Modulation for User Attribution and Fingerprinting in Te
        17160, -- 2306.05178 SyncDiffusion: Coherent Montage via Synchronized Joint Diffusions
        17173, -- 2306.05357 Unsupervised Compositional Concepts Discovery with Text-to-Image Gener
        17271, -- 2306.06638 Face0: Instantaneously Conditioning a Text-to-Image Model on a Face
        17318, -- 2306.07280 Controlling Text-to-Image Diffusion by Orthogonal Finetuning
        17378, -- 2306.07954 Rerender A Video: Zero-Shot Text-Guided Video-to-Video Translation
        17404, -- 2306.08247 Diffusion in Diffusion: Cyclic One-Way Diffusion for Text-Vision-Condi
        17448, -- 2306.08877 Linguistic Binding in Diffusion Models: Enhancing Attribute Correspond
        17497, -- 2306.09345 Evaluating Data Attribution for Text-to-Image Models
        17537, -- 2306.09864 AvatarBooth: High-Quality and Customizable 3D Human Avatar Generation
        17560, -- 2306.10169 Meta-Personalizing Vision-Language Models to Find Named Instances in V
        17674, -- 2306.12624 DreamEdit: Subject-driven Image Editing
        17711, -- 2306.13455 DreamEditor: Text-Driven 3D Scene Editing with Neural Fields
        17749, -- 2306.14153 DomainStudio: Fine-Tuning Diffusion Models for Domain-Driven Image Gen
        17877, -- 2306.16894 PFB-Diff: Progressive Feature Blending Diffusion for Text-driven Image
        17883, -- 2306.16928 One-2-3-45: Any Single Image to 3D Mesh in 45 Seconds without Per-Shap
        17897, -- 2306.17140 ID-Pose: Sparse-view Camera Pose Estimation by Inverting Diffusion Mod
        17898, -- 2306.17154 Generate Anything Anywhere in Any Scene
        17938, -- 2307.00300 DreamIdentity: Improved Editability for Efficient Face-identity Preser
        18006, -- 2307.01952 SDXL: Improving Latent Diffusion Models for High-Resolution Image Synt
        18045, -- 2307.02698 Dequantization and Color Transfer with Diffusion Models
        18060, -- 2307.03108 DIAGNOSIS: Detecting Unauthorized Data Usages in Text-to-image Diffusi
        18134, -- 2307.04725 AnimateDiff: Animate Your Personalized Text-to-Image Diffusion Models
        18140, -- 2307.04787 Collaborative Score Distillation for Consistent Visual Synthesis
        18214, -- 2307.06925 Domain-Agnostic Tuning-Encoder for Fast Personalization of Text-To-Ima
        18216, -- 2307.06940 Animate-A-Story: Storytelling with Retrieval-Augmented Video Generatio
        18218, -- 2307.06945 In-context Autoencoder for Context Compression in a Large Language Mod
        18291, -- 2307.08182 Zero-Shot Image Harmonization with Generative Model Prior
        18382, -- 2307.09481 AnyDoor: Zero-shot Object-level Image Customization
        18397, -- 2307.09756 Generative Prompt Model for Weakly Supervised Object Localization
        18400, -- 2307.09781 Text2Layer: Layered Image Generation using Latent Diffusion Model
        18416, -- 2307.10159 FABRIC: Personalizing Diffusion Models with Iterative Feedback
        18453, -- 2307.10711 AdjointDPM: Adjoint Sensitivity Method for Gradient Backpropagation of
        18464, -- 2307.10816 BoxDiff: Text-to-Image Synthesis with Training-Free Box-Constrained Di
        18487, -- 2307.11118 Diffusion Sampling with Momentum for Mitigating Divergence Artifacts
        18503, -- 2307.11410 Subject-Diffusion:Open Domain Personalized Text-to-Image Generation wi
        18561, -- 2307.12493 TF-ICON: Diffusion-Based Training-Free Cross-Domain Image Composition
        18667, -- 2307.14331 Visual Instruction Inversion: Image Editing via Visual Prompting
        18672, -- 2307.14352 General Image-to-Image Translation with One-Shot Image Guidance
        18676, -- 2307.14397 A Survey on Generative Modeling with Limited Data, Few Shots, and Zero
        18684, -- 2307.14611 TextManiA: Enriching Visual Feature by Text-driven Manifold Augmentati
        18725, -- 2307.15199 PromptStyler: Prompt-driven Style Generation for Source-free Domain Ge
        18846, -- 2308.00906 ImageBrush: Learning Visual In-Context Instructions for Exemplar-Based
        18879, -- 2308.01508 Circumventing Concept Erasure Methods For Text-to-Image Generative Mod
        18921, -- 2308.02205 GEMRec: Towards Generative Model Recommendation
        18947, -- 2308.02669 ConceptLab: Creative Concept Generation using VLM-Guided Diffusion Pri
        19000, -- 2308.03463 DiffSynth: Latent In-Iteration Deflickering for Realistic Video Synthe
        19044, -- 2308.04288 Cloth2Tex: A Customized Cloth Texture Generation Pipeline for 3D Virtu
        19200, -- 2308.06721 IP-Adapter: Text Compatible Image Prompt Adapter for Text-to-Image Dif
        19334, -- 2308.08545 TeCH: Text-guided Reconstruction of Lifelike Clothed Humans
        19422, -- 2308.09592 StableVideo: Text-driven Consistency-aware Diffusion Video Editing
        19483, -- 2308.10103 ASPIRE: Language-Guided Data Augmentation for Improving Robustness Aga
        19831, -- 2308.14078 Sparse3D: Distilling Multiview-Consistent Diffusion for Object Reconst
        19839, -- 2308.14177 AI-Generated Content (AIGC) for Various Data Modalities: A Survey
        19841, -- 2308.14191 SketchDreamer: Interactive Text-Augmented Creative Sketch Ideation
        19980, -- 2308.16777 Ref-Diff: Zero-shot Referring Image Segmentation with Generative Model
        20088, -- 2309.01770 StyleAdapter: A Unified Stylized Image Generation Model
        20162, -- 2309.03179 SLiMe: Segment Like Me
        20175, -- 2309.03453 SyncDreamer: Generating Multiview-consistent Images from a Single-view
        20184, -- 2309.03599 Chasing Consistency in Text-to-3D Generation from a Single Image
        20292, -- 2309.05519 NExT-GPT: Any-to-Any Multimodal LLM
        20296, -- 2309.05569 ITI-GEN: Inclusive Text-to-Image Generation
        20305, -- 2309.05793 PhotoVerse: Tuning-Free Image Customization with Text-to-Image Diffusi
        20319, -- 2309.06135 Prompting4Debugging: Red-Teaming Text-to-Image Diffusion Models by Fin
        20363, -- 2309.06895 MagiCapture: High-Resolution Multi-Concept Portrait Customization
        20366, -- 2309.06933 DreamStyler: Paint by Style Inversion with Text-to-Image Diffusion Mod
        20596, -- 2309.10279 360$^\circ$ Reconstruction From a Single Image Using Space Carved Outp
        20689, -- 2309.11497 FreeU: Free Lunch in Diffusion U-Net
        20690, -- 2309.11499 DreamLLM: Synergistic Multimodal Comprehension and Creation
        20740, -- 2309.12302 Text-Guided Vector Graphics Customization
        20899, -- 2309.14339 Chop & Learn: Recognizing and Generating Object-State Compositions
        20908, -- 2309.14494 Free-Bloom: Zero-Shot Text-to-Video Generator with LLM Director and LD
        20969, -- 2309.15508 DreamCom: Finetuning Text-guided Inpainting Model for Image Compositio
        20972, -- 2309.15535 From LAION-5B to LAION-EO: Filtering Billions of Images Using Anchor D
        20978, -- 2309.15664 Dynamic Prompt Learning: Addressing Cross-Attention Leakage for Text-B
        20984, -- 2309.15807 Emu: Enhancing Image Generation Models Using Photogenic Needles in a H
        20988, -- 2309.15842 Exploiting the Signal-Leak Bias in Diffusion Models
        21046, -- 2309.16668 RealFill: Reference-Driven Generation for Authentic Image Completion
        21090, -- 2309.17261 Consistent123: One Image to Highly Consistent 3D Asset Using Case-Awar
        21115, -- 2310.00031 Text-image Alignment for Diffusion-based Perception
        21217, -- 2310.01110 Prompt-tuning latent diffusion models for inverse problems
        21264, -- 2310.01506 Direct Inversion: Boosting Diffusion-based Editing with 3 Lines of Cod
        21271, -- 2310.01596 ImagenHub: Standardizing the evaluation of conditional image generatio
        21283, -- 2310.01701 Transcending Domains through Text-to-Image Diffusion: A Source-Free Ap
        21304, -- 2310.01830 AI-Generated Images as Data Source: The Dawn of Synthetic Era
        21356, -- 2310.02426 EditVal: Benchmarking Diffusion Based Text-Guided Image Editing Method
        21398, -- 2310.02992 Kosmos-G: Generating Images in Context with Multimodal Large Language
        21473, -- 2310.03739 Aligning Text-to-Image Diffusion Models with Reward Backpropagation
        21621, -- 2310.05473 Sentence-level Prompts Benefit Composed Image Retrieval
        21702, -- 2310.06347 JointNet: Extending Text-to-Image Diffusion for Dense Distribution Mod
        21726, -- 2310.06744 HiFi-123: Towards High-fidelity One Image to 3D Content Generation
        21749, -- 2310.06968 ObjectComposer: Consistent Generation of Multiple Objects Without Fine
        21768, -- 2310.07204 State of the Art on Diffusion Models for Visual Computing
        21792, -- 2310.07419 Multi-Concept T2I-Zero: Tweaking Only The Text Embeddings and Nothing
        21850, -- 2310.08094 SingleInsert: Inserting New Concepts from a Single Image into Text-to-
        21855, -- 2310.08129 Tailored Visions: Enhancing Text-to-Image Generation with Personalized
        21967, -- 2310.09291 Vision-by-Language for Training-Free Compositional Image Retrieval
        22034, -- 2310.10343 ConsistNet: Enforcing 3D Consistency for Multi-view Images Diffusion
        22066, -- 2310.10644 TOSS:High-quality Text-guided Novel View Synthesis from a Single Image
        22159, -- 2310.11868 To Generate or Not? Safety-Driven Unlearned Diffusion Models Are Still
        22187, -- 2310.12274 An Image is Worth Multiple Words: Discovering Object Level Concepts us
        22309, -- 2310.13772 TexFusion: Synthesizing 3D Textures with Text-Guided Image Diffusion M
        22314, -- 2310.13828 Nightshade: Prompt-Specific Poisoning Attacks on Text-to-Image Generat
        22490, -- 2310.16002 Integrating View Conditions for Image Synthesis
        22526, -- 2310.16400 Fuse Your Latents: Video Editing with Multi-source Latent Diffusion Mo
        22613, -- 2310.17569 SD4Match: Learning to Prompt Stable Diffusion Model for Semantic Match
        22671, -- 2310.18308 Gen2Sim: Scaling up Robot Learning in Simulation with Generative Model
        22714, -- 2310.18840 Customizing 360-Degree Panoramas through Text-to-Image Diffusion Model
        22771, -- 2310.19784 CustomNet: Zero-shot Object Customization with Variable-Viewpoints in
        22836, -- 2311.00213 Consistent Video-to-Video Transfer Using Synthetic Dataset
        22864, -- 2311.00618 De-Diffusion Makes Text a Strong Cross-Modal Interface
        22886, -- 2311.00990 VideoDreamer: Customized Multi-Subject Text-to-Video Generation with D
        22910, -- 2311.01410 The Blessing of Randomness: SDE Beats ODE in General Diffusion-based I
        22956, -- 2311.02343 Stable Diffusion Reference Only: Image Prompt and Blueprint Jointly Gu
        22984, -- 2311.03054 AnyText: Multilingual Visual Text Generation And Editing
        23129, -- 2311.05461 Control3D: Towards Controllable Text-to-3D Generation
        23175, -- 2311.06243 Parameter-Efficient Orthogonal Finetuning via Butterfly Factorization
        23207, -- 2311.06792 IMPUS: Image Morphing with Perceptually-Uniform Sampling Using Diffusi
        23262, -- 2311.07604 Finetuning Text-to-Image Diffusion Models for Fairness
        23391, -- 2311.09221 Single-Image 3D Human Digitization with Shape-Guided Diffusion
        23396, -- 2311.09257 UFOGen: You Forward Once Large Scale Text-to-Image Generation via Diff
        23398, -- 2311.09265 FastBlend: a Powerful Model-Free Toolkit Making Video Stylization Easi
        23418, -- 2311.09571 3D Paintbrush: Local Stylization of 3D Shapes with Cascaded Score Dist
        23465, -- 2311.10093 The Chosen One: Consistent Characters in Text-to-Image Diffusion Model
        23468, -- 2311.10123 MetaDreamer: Efficient Text-to-3D Creation With Disentangling Geometry
        23473, -- 2311.10329 High-fidelity Person-centric Subject-to-Image Synthesis
        23496, -- 2311.10794 Text-to-Sticker: Style Tailoring Latent Diffusion Models for Human Exp
        23519, -- 2311.11243 AutoStory: Generating Diverse Storytelling Images with Minimal Human E
        23546, -- 2311.11697 Cut-and-Paste: Subject-Driven Video Editing with Attention Control
        23577, -- 2311.12092 Concept Sliders: LoRA Adaptors for Precise Control in Diffusion Models
        23624, -- 2311.12832 Toward effective protection against diffusion based mimicry through sc
        23677, -- 2311.13600 ZipLoRA: Any Subject in Any Style by Effectively Merging LoRAs
        23714, -- 2311.14343 Highly Detailed and Temporal Consistent Video Stylization via Synchron
        23726, -- 2311.14603 Animate124: Animating One Image to 4D Dynamic Scene
        23752, -- 2311.15040 InstaStyle: Inversion Noise of a Stylized Image is Secretly a Style Ad
        23793, -- 2311.15648 Reinforcement Learning from Diffusion Feedback: Q* for Image Search
        23794, -- 2311.15657 Enhancing Diffusion Models with Text-Encoder Reinforcement Learning
        23809, -- 2311.15841 Learning Disentangled Identifiers for Action-Customized Text-to-Image
        23849, -- 2311.16424 Manifold Preserving Guided Diffusion
        23850, -- 2311.16432 Text-Driven Image Editing via Learnable Regions
        23869, -- 2311.16567 MobileDiffusion: Instant Text-to-Image Generation on Mobile Devices
        23873, -- 2311.16711 LEDITS++: Limitless Image Editing using Text-to-Image Models
        23877, -- 2311.16739 As-Plausible-As-Possible: Plausibility-Aware Mesh Deformation Using 2D
        23892, -- 2311.16933 SparseCtrl: Adding Sparse Controls to Text-to-Video Diffusion Models
        23915, -- 2311.17082 DreamPropeller: Supercharge Text-to-3D Generation with Parallel Sampli
        23930, -- 2311.17137 Generative Models: What Do They Know? Do They Know Things? Let's Find
        23949, -- 2311.17461 When StyleGAN Meets Stable Diffusion: a $\mathscr{W}_+$ Adapter for Pe
        23969, -- 2311.17717 Receler: Reliable Concept Erasing of Text-to-Image Diffusion Models vi
        24038, -- 2311.18654 Detailed Human-Centric Text Description-Driven Large Scene Synthesis
        24061, -- 2311.18830 MotionEditor: Editing Video Motion via Content-Aware Diffusion
        24099, -- 2312.00330 StyleCrafter: Enhancing Stylized Text-to-Video Generation with Style A
        24106, -- 2312.00375 Text-Guided 3D Face Synthesis -- From Generation to Editing
        24133, -- 2312.00739 Adversarial Score Distillation: When score distillation meets GAN
        24139, -- 2312.00777 VideoBooth: Diffusion-based Video Generation with Image Prompts
        24147, -- 2312.00845 VMC: Video Motion Customization using Temporal Attention Adaption for
        24155, -- 2312.00870 3DiFACE: Diffusion-based Speech-driven 3D Facial Animation and Editing
        24197, -- 2312.01663 Customize your NeRF: Adaptive Source Driven 3D Scene Editing via Local
        24224, -- 2312.02087 VideoSwap: Customized Video Subject Swapping with Interactive Semantic
        24225, -- 2312.02109 ArtAdapter: Text-to-Image Style Transfer using Multi-Level Style Encod
        24230, -- 2312.02133 Style Aligned Image Generation via Shared Attention
        24233, -- 2312.02139 DiffiT: Diffusion Vision Transformers for Image Generation
        24249, -- 2312.02212 Portrait Diffusion: Training-free Face Stylization with Chain-of-Paint
        24255, -- 2312.02238 X-Adapter: Adding Universal Compatibility of Plugins for Upgraded Diff
        24271, -- 2312.02432 Orthogonal Adaptation for Modular Customization of Diffusion Models
        24282, -- 2312.02568 Prompt2NeRF-PIL: Fast NeRF Generation via Pretrained Implicit Latent
        24292, -- 2312.02696 Analyzing and Improving the Training Dynamics of Diffusion Models
        24300, -- 2312.02813 BIVDiff: A Training-Free Framework for General-Purpose Video Synthesis
        24305, -- 2312.02919 Fine-grained Controllable Video Generation via Object Appearance and C
        24314, -- 2312.02970 Alchemist: Parametric Control of Material Properties with Diffusion Mo
        24321, -- 2312.03011 InstructBooth: Instruction-following Personalized Text-to-Image Genera
        24327, -- 2312.03045 Customization Assistant for Text-to-image Generation
        24329, -- 2312.03047 MagicStick: Controllable Video Editing via Control Handle Transformati
        24332, -- 2312.03079 LooseControl: Lifting ControlNet for Generalized Depth Conditioning
        24335, -- 2312.03154 ViscoNet: Bridging and Harmonizing Visual and Textual Conditioning for
        24357, -- 2312.03556 Personalized Face Inpainting with Diffusion Models by Parallel Visual
        24358, -- 2312.03584 Context Diffusion: In-Context Aware Image Generation
        24359, -- 2312.03587 Language-Informed Visual Concept Learning
        24360, -- 2312.03594 A Task is Worth One Word: Learning with Task Prompts for High-Quality
        24388, -- 2312.03771 DreamInpainter: Text-Guided Subject-Driven Image Inpainting with Diffu
        24389, -- 2312.03772 DiffusionAtlas: High-Fidelity Consistent Diffusion Video Editing
        24398, -- 2312.03816 AVID: Any-Length Video Inpainting with Diffusion Model
        24430, -- 2312.04364 DemoCaricature: Democratising Caricature Generation with a Rough Sketc
        24437, -- 2312.04461 PhotoMaker: Customizing Realistic Human Photos via Stacked ID Embeddin
        24448, -- 2312.04524 RAVE: Randomized Noise Shuffling for Fast and Consistent Video Editing
        24463, -- 2312.04560 NeRFiller: Completing Scenes via Generative 3D Inpainting
        24474, -- 2312.04655 ECLIPSE: A Resource-Efficient Text-to-Image Prior for Image Generation
        24486, -- 2312.04831 Towards Enhanced Image Inpainting: Mitigating Unwanted Object Insertio
        24490, -- 2312.04884 UDiffText: A Unified Framework for High-quality Text Synthesis in Arbi
        24499, -- 2312.04966 NewMove: Customizing text-to-video models with novel motions
        24521, -- 2312.05288 MotionCrafter: One-Shot Motion Customization of Diffusion Models
        24563, -- 2312.05856 A Video is Worth 256 Bases: Spatial-Temporal Expectation-Maximization
        24572, -- 2312.06038 Correcting Diffusion Generation through Resampling
        24590, -- 2312.06354 PortraitBooth: A Versatile Portrait Model for Fast Identity-preserved
        24601, -- 2312.06573 ControlNet-XS: Rethinking the Control of Text-to-Image Diffusion Model
        24696, -- 2312.07536 FreeControl: Training-Free Spatial Control of Any Text-to-Image Diffus
        24725, -- 2312.08056 Knowledge-Aware Artifact Image Synthesis with LLM-Enhanced Prompting a
        24771, -- 2312.08873 Diffusion Cocktail: Mixing Domain-Specific Diffusion Models for Divers
        24800, -- 2312.09168 DiffusionLight: Light Probes for Free by Painting a Chrome Ball
        24811, -- 2312.09246 SHAP-EDITOR: Instruction-guided Latent 3D Editing in Seconds
        24816, -- 2312.09256 LIME: Localized Image Editing via Attention Regularization in Diffusio
        24837, -- 2312.09608 Faster Diffusion: Rethinking the Role of the Encoder for Diffusion Mod
        24857, -- 2312.10113 Focus on Your Instruction: Fine-grained and Multi-instruction Image Ed
        24894, -- 2312.10656 VidToMe: Video Token Merging for Zero-Shot Video Editing
        24905, -- 2312.10835 Your Student is Better Than Expected: Adaptive Teacher-Student Collabo
        24907, -- 2312.10899 MagicScroll: Nontypical Aspect-Ratio Image Generation for Visual Story
        24954, -- 2312.11595 SPIRE: Semantic Prompt-Driven Image Restoration
        24964, -- 2312.11826 Decoupled Textual Embeddings for Customized Image Generation
        24973, -- 2312.12030 Towards Accurate Guided Diffusion Sampling through Symplectic Adjoint
        24997, -- 2312.12419 Scene-Conditional 3D Object Stylization and Composition
        25015, -- 2312.12540 Lightning-Fast Image Inversion and Editing for Text-to-Image Diffusion
        25052, -- 2312.13271 Repaint123: Fast and High-quality One Image to 3D Generation with Prog
        25054, -- 2312.13286 Generative Multimodal Models are In-Context Learners
        25073, -- 2312.13663 Free-Editor: Zero-shot Text-driven 3D Scene Editing
        25075, -- 2312.13691 DreamTuner: Single Image is Enough for Subject-Driven Generation
        25097, -- 2312.14091 HD-Painter: High-Resolution and Prompt-Faithful Text-Guided Image Inpa
        25111, -- 2312.14216 DreamDistribution: Learning Prompt Distribution for Diverse In-distrib
        25140, -- 2312.14867 VIEScore: Towards Explainable Metrics for Conditional Image Synthesis
        25167, -- 2312.15247 Prompt-Propose-Verify: A Reliable Hand-Object-Interaction Data Generat
        25190, -- 2312.15707 High-Fidelity Diffusion-based Image Editing
        25211, -- 2312.15980 HarmonyView: Harmonizing Consistency and Diversity in One-Image-to-3D
        25222, -- 2312.16145 One-Dimensional Adapter to Rule Them All: Concepts, Diffusion Models a
        25227, -- 2312.16204 Learning from Mistakes: Iterative Prompt Relabeling for Text-to-Image
        25232, -- 2312.16272 SSR-Encoder: Encoding Selective Subject Representation for Subject-Dri
        25277, -- 2312.17161 Restoration by Generation with Constrained Priors
        25281, -- 2312.17225 4DGen: Grounded 4D Content Generation with Spatial-temporal Consistenc
        25284, -- 2312.17234 Personalized Restoration via Dual-Pivot Tuning
        25292, -- 2312.17250 iFusion: Inverting Diffusion for Pose-Free Reconstruction from Sparse
        25500, -- 2401.02473 VASE: Object-Centric Appearance and Shape Manipulation of Real Videos
        25601, -- 2401.04339 Memory-Efficient Fine-Tuning for Quantized Diffusion Model
        25757, -- 2401.06578 360DVD: Controllable Panorama Video Generation with 360-Degree Video D
        25946, -- 2401.09416 TextureDreamer: Image-guided Texture Synthesis through Geometry-aware
        25974, -- 2401.09742 Image Translation as Diffusion Visual Programmers
        25987, -- 2401.09962 CustomVideo: Customizing Text-to-Video Generation with Multiple Subjec
        26069, -- 2401.11078 UltrAvatar: A Realistic Animatable 3D Avatar Diffusion Model with Auth
        26139, -- 2401.12179 DITTO: Diffusion Inference-Time T-Optimization for Music Generation
        26229, -- 2401.13388 UNIMO-G: Unified Image Generation through Multimodal Conditional Diffu
        26253, -- 2401.13795 Diffuse to Choose: Enriching Image Conditioned Inpainting in Latent Di
        26266, -- 2401.13974 BootPIG: Bootstrapping Zero-shot Personalized Image Generation Capabil
        26276, -- 2401.14066 CreativeSynth: Cross-Art-Attention for Artistic Image Synthesis with M
        26305, -- 2401.14398 pix2gestalt: Amodal Segmentation by Synthesizing Wholes
        26338, -- 2401.14828 TIP-Editor: An Accurate 3D Editor Following Both Text-Prompts And Imag
        26381, -- 2401.15687 Media2Face: Co-speech Facial Animation Generation With Multi-Modality
        26383, -- 2401.15708 Object-Driven One-Shot Fine-tuning of Text-to-Image Diffusion with Pro
        26405, -- 2401.15975 StableIdentity: Inserting Anybody into Anywhere at First Sight
        26419, -- 2401.16224 Diffutoon: High-Resolution Editable Toon Shading via Diffusion Models
        26467, -- 2401.16762 Pick-and-Draw: Training-free Semantic Guidance for Text-to-Image Perso
        26473, -- 2401.16861 Repositioning the Subject within Image
        26482, -- 2401.17053 BlockFusion: Expandable 3D Scene Generation using Latent Tri-plane Ext
        26526, -- 2401.17807 Advances in 3D Generation: A Survey
        26549, -- 2401.18085 Motion Guidance: Diffusion-Based Image Editing with Differentiable Mot
        26576, -- 2402.00631 Beyond Inserting: Learning Identity Embedding for Semantic-Fidelity Pe
        26826, -- 2402.03162 Direct-a-Video: Customized Video Generation with User-Directed Camera
        26836, -- 2402.03286 Training-Free Consistent Text-to-Image Generation
        26860, -- 2402.03501 An Inpainting-Infused Pipeline for Attire and Background Replacement
        26864, -- 2402.03549 AnaMoDiff: 2D Analogical Motion Diffusion via Disentangled Denoising
        26999, -- 2402.04929 Source-Free Domain Adaptation with Diffusion-Guided Source Data Genera
        27021, -- 2402.05195 $λ$-ECLIPSE: Multi-Concept Personalized Text-to-Image Diffusion Models
        27027, -- 2402.05375 Get What You Want, Not What You Don't: Image Content Suppression for T
        27104, -- 2402.06149 HeadStudio: Text to Animatable Head Avatars with 3D Gaussian Splatting
        27262, -- 2402.08601 Latent Inversion with Timestep-aware Sampling for Training-free Non-ri
        27268, -- 2402.08654 Learning Continuous 3D Words for Text-to-Image Generation
        27282, -- 2402.08714 PRDP: Proximal Reward Difference Prediction for Large-Scale Reward Fin
        27351, -- 2402.09812 DreamMatcher: Appearance Matching Self-Attention for Semantically-Cons
        27363, -- 2402.09966 Textual Localization: Decomposing Multi-concept Images for Subject-Dri
        27366, -- 2402.10009 Zero-Shot Unsupervised and Text-Based Audio Editing Using DDPM Inversi
        27386, -- 2402.10210 Self-Play Fine-Tuning of Diffusion Models for Text-to-Image Generation
        27551, -- 2402.11849 ComFusion: Personalized Subject Generation in Multiple Specific Scenes
        27663, -- 2402.12974 Visual Style Prompting with Swapping Self-Attention
        27832, -- 2402.14780 Customize-A-Video: One-Shot Motion Customization of Text-to-Video Diff
        27907, -- 2402.15504 Gen4Gen: Generative Data Pipeline for Generative Multi-Concept Composi
        28025, -- 2402.17113 Transparent Image Layer Diffusion using Latent Transparency
        28055, -- 2402.17412 DiffuseKronA: A Parameter Efficient Fine-tuning Method for Personalize
        28067, -- 2402.17525 Diffusion Model-Based Image Editing: A Survey
        28176, -- 2402.18842 ViewFusion: Towards Multi-View Consistency via Interpolated Denoising
        28241, -- 2403.00483 RealCustom: Narrowing Real Text Word for Real-Time Open-Domain Text-to
        28291, -- 2403.01108 Face Swap via Diffusion Model
        28326, -- 2403.01505 SCott: Accelerating Diffusion Models with Stochastic Consistency Disti
        28342, -- 2403.01779 OOTDiffusion: Outfitting Fusion based Latent Diffusion for Controllabl
        28508, -- 2403.04437 StableDrag: Stable Dragging for Point-based Image Editing
        28546, -- 2403.04880 An Item is Worth a Prompt: Versatile Image Editing with Disentangled C
        28556, -- 2403.05016 DiffClass: Diffusion-Based Class Incremental Learning
        28563, -- 2403.05053 PrimeComposer: Faster Progressively Combined Diffusion for Image Compo
        28567, -- 2403.05094 Face2Diffusion for Fast and Editable Face Personalization
        28570, -- 2403.05139 Improving Diffusion Models for Authentic Virtual Try-on in the Wild
        28588, -- 2403.05438 VideoElevator: Elevating Video Generation Quality with Versatile Text-
        28644, -- 2403.06381 Enhancing Semantic Fidelity in Text-to-Image Synthesis: Attention Regu
        28666, -- 2403.06775 FaceChain-SuDe: Building Derived Class to Inherit Category Attributes
        28682, -- 2403.06951 DEADiff: An Efficient Stylization Diffusion Model with Disentangled Re
        28718, -- 2403.07500 Block-wise LoRA: Revisiting Fine-grained LoRA for Effective Personaliz
        28738, -- 2403.07764 Stable-Makeup: When Real-World Makeup Transfer Meets Diffusion Model
        28748, -- 2403.07860 Bridging Different Language Models and Generative Vision Models for Te
        28873, -- 2403.09625 Make-Your-3D: Fast and Consistent Subject-Driven 3D Content Generation
        28910, -- 2403.10179 Animate Your Motion: Turning Still Images into Dynamic Videos
        28953, -- 2403.10783 StableGarment: Garment-Centric Generation via Stable Diffusion
        28967, -- 2403.10983 OMG: Occlusion-friendly Personalized Multi-concept Generation in Diffu
        28974, -- 2403.11053 OSTAF: A One-Shot Tuning Method for Improved Attribute-Focused T2I Per
        28978, -- 2403.11105 Source Prompt Disentangled Inversion for Boosting Image Editability wi
        29018, -- 2403.11568 EffiVED:Efficient Video Editing via Text-instruction Diffusion Models
        29023, -- 2403.11627 LoRA-Composer: Leveraging Low-Rank Adaptation for Multi-Concept Custom
        29024, -- 2403.11641 Arc2Face: A Foundation Model for ID-Consistent Human Faces
        29035, -- 2403.11781 Infinite-ID: Identity-preserved Personalization via ID-semantics Decou
        29105, -- 2403.12585 LASPA: Latent Spatial Alignment for Fast Training-free Single Image Ed
        29109, -- 2403.12658 Tuning-Free Image Customization with Image and Text Guidance
        29130, -- 2403.12906 TexDreamer: Towards Zero-Shot High-Fidelity 3D Human Texture Generatio
        29141, -- 2403.12962 FRESCO: Spatial-Temporal Correspondence for Zero-Shot Video Translatio
        29191, -- 2403.13535 IDAdapter: Learning Mixed Features for Tuning-Free Personalization of
        29195, -- 2403.13551 Ground-A-Score: Scaling Up the Score Distillation for Multi-Attribute
        29235, -- 2403.14148 Efficient Video Diffusion Models via Content-Frame Motion-Latent Decom
        29244, -- 2403.14291 Open-Vocabulary Attention Maps with Token Optimization for Semantic Se
        29271, -- 2403.14572 Implicit Style-Content Separation using B-LoRA
        29274, -- 2403.14599 MyVLM: Personalizing VLMs for User-Specific Queries
        29276, -- 2403.14608 Parameter-Efficient Fine-Tuning for Large Models: A Comprehensive Surv
        29300, -- 2403.14790 Latent Diffusion Models for Attribute-Preserving Image Anonymization
        29308, -- 2403.14966 DreamFlow: High-Quality Text-to-3D Generation by Approximating Probabi
        29315, -- 2403.15059 MM-Diff: High-Fidelity Image Personalization via Multi-Modal Condition
        29334, -- 2403.15362 CoLLEGe: Concept Embedding Generation for Large Language Models
        29339, -- 2403.15383 ThemeStation: Generating Theme-Aware 3D Assets from Few Exemplars
        29402, -- 2403.16422 Refining Text-to-Image Generation: Towards Accurate Training-Free Glyp
        29445, -- 2403.17005 TRIP: Temporal Residual Learning with Image Noise Prior for Image-to-V
        29448, -- 2403.17008 FlashFace: Human Image Personalization with High-fidelity Identity Pre
        29450, -- 2403.17064 Continuous, Subject-Specific Attribute Control in T2I Models by Identi
        29526, -- 2403.18211 NeuroPictor: Refining fMRI-to-Image Reconstruction via Multi-individua
        29546, -- 2403.18461 DiffStyler: Diffusion-based Localized Image Style Transfer
        29549, -- 2403.18551 Attention Calibration for Disentangled Text-to-Image Personalization
        29554, -- 2403.18660 InstructBrush: Learning Attention-based Instruction Optimization for I
        29595, -- 2403.19235 DreamSalon: A Staged Diffusion Framework for Preserving Identity-Conte
        29638, -- 2403.19776 CLoRA: A Contrastive Approach to Compose Multiple LoRA Models
        29666, -- 2403.20193 Motion Inversion for Video Customization
        29669, -- 2403.20249 Relation Rectification in Diffusion Model
        29745, -- 2404.00878 TryOn-Adapter: Efficient Fine-Grained Clothing Identity Adaptation for
        29746, -- 2404.00879 Model-Agnostic Human Preference Inversion in Diffusion Models
        29767, -- 2404.01089 Texture-Preserving Diffusion Models for High-Fidelity Virtual Try-On
        29788, -- 2404.01291 Evaluating Text-to-Visual Generation with Image-to-Text Generation
        29800, -- 2404.01342 DiffAgent: Fast and Accurate Text-to-Image API Selection with Large La
        29854, -- 2404.02125 3D Congealing: 3D-Aware Image Alignment in the Wild
        29887, -- 2404.02733 InstantStyle: Free Lunch towards Style-Preserving in Text-to-Image Gen
        29955, -- 2404.03620 LCM-Lookahead for Encoder-based Text-to-Image Personalization
        29972, -- 2404.03736 SC4D: Sparse-Controlled Video-to-4D Generation and Motion Transfer
        29984, -- 2404.03913 Concept Weaver: Enabling Multi-Concept Fusion in Text-to-Image Models
        30000, -- 2404.04243 Identity Decoupling for Multi-Subject Personalization of Text-to-Image
        30063, -- 2404.05256 StyleForge: Enhancing Text-to-Image Synthesis for Any Artistic Styles
        30065, -- 2404.05331 Mask-ControlNet: Higher-Quality Image Generation with An Additional Ma
        30081, -- 2404.05595 UniFL: Improve Latent Diffusion Model via Unified Feedback Learning
        30092, -- 2404.05674 MoMA: Multimodal LLM Adapter for Fast Personalized Image Generation
        30096, -- 2404.05717 SwapAnything: Enabling Arbitrary Object Swapping in Personalized Visua
        30149, -- 2404.06451 SmartControl: Enhancing ControlNet for Handling Rough Visual Condition
        30159, -- 2404.06637 GeoSynth: Contextually-Aware High-Resolution Satellite Image Synthesis
        30191, -- 2404.07178 Move Anything with Layered Scene Diffusion
        30216, -- 2404.07554 CAT: Contrastive Adapter Training for Personalized Image Generation
        30224, -- 2404.07724 Applying Guidance in a Limited Interval Improves Sample and Distributi
        30253, -- 2404.07987 ControlNet++: Improving Conditional Controls with Efficient Consistenc
        30255, -- 2404.07990 OpenBias: Open-set Bias Detection in Text-to-Image Generative Models
        30350, -- 2404.09512 Magic Clothing: Controllable Garment-Driven Image Synthesis
        30384, -- 2404.09967 Ctrl-Adapter: An Efficient and Versatile Framework for Adapting Divers
        30406, -- 2404.10267 OneActor: Consistent Character Generation via Cluster-Conditioned Guid
        30475, -- 2404.11565 MoA: Mixture-of-Attention for Subject-Context Disentanglement in Perso
        30495, -- 2404.11925 EdgeFusion: On-Device Text-to-Image Generation
        30530, -- 2404.12333 Customizing Text-to-Image Diffusion with Object Viewpoint Control
        30617, -- 2404.13628 Mixture of LoRA Experts
        30633, -- 2404.13944 Gorgeous: Create Your Desired Character Facial Makeup from Any Ideas
        30646, -- 2404.14239 MultiBooth: Towards Generating All Your Concepts in an Image from Text
        30671, -- 2404.14568 UVMap-ID: A Controllable and Personalized UV Map Generative Model
        30711, -- 2404.15267 From Parts to Whole: A Unified Reference Framework for Controllable Hu
        30713, -- 2404.15275 ID-Animator: Zero-Shot Identity-Preserving Human Video Generation
        30729, -- 2404.15677 CharacterFactory: Sampling Consistent Characters with GANs for Diffusi
        30746, -- 2404.16022 PuLID: Pure and Lightning ID Customization via Contrastive Alignment
        30771, -- 2404.16612 MuseumMaker: Continual Style Customization without Catastrophic Forget
        30785, -- 2404.16771 ConsistentID: Portrait Generation with Multimodal Fine-Grained Identit
        30823, -- 2404.17364 MV-VTON: Multi-View Virtual Try-On with Diffusion Models
        30831, -- 2404.17569 MaPa: Text-driven Photorealistic Material Painting for 3D Shapes
        30868, -- 2404.18212 Paint by Inpaint: Learning to Add Image Objects by Removing Them First
        30902, -- 2404.18928 Stylus: Automatic Adapter Selection for Diffusion Models
        30925, -- 2404.19427 InstantFamily: Masked Attention for Zero-shot Multi-ID Image Generatio
        30961, -- 2405.00313 Streamlining Image Editing with Layered Diffusion Brushes
        31012, -- 2405.01434 StoryDiffusion: Consistent Self-Attention for Long-Range Image and Vid
        31023, -- 2405.01536 Customizing Text-to-Image Models with a Single Image Pair
        31079, -- 2405.03150 Video Diffusion Models: A Survey
        31169, -- 2405.05806 MasterWeaver: Taming Editability and Face Identity for Personalized Te
        31179, -- 2405.05967 Distilling Diffusion Models into Conditional GANs
        31214, -- 2405.06948 Training-free Subject-Enhanced Attention Guidance for Compositional Te
        31219, -- 2405.07288 Erasing Concepts from Text-to-Image Diffusion Models with Few-shot Unl
        31476, -- 2405.12914 An Empirical Study and Analysis of Text-to-Image Generation Using Larg
        31481, -- 2405.12970 Face Adapter for Pre-Trained Diffusion Models with Fine-Grained ID and
        31483, -- 2405.12978 Personalized Residuals for Concept-Driven Text-to-Image Generation
        31539, -- 2405.13870 FreeCustom: Tuning-Free Customized Image Generation for Multi-Concept
        31566, -- 2405.14201 FreeTuner: Any Subject in Any Style with Training-free Diffusion
        31606, -- 2405.14677 RectifID: Personalizing Rectified Flow with Anchored Classifier Guidan
        31650, -- 2405.15020 AdjointDEIS: Efficient Gradients for Diffusion Models
        31671, -- 2405.15234 Defensive Unlearning with Adversarial Training for Robust Concept Eras
        31757, -- 2405.16341 R.A.C.E.: Robust Adversarial Concept Erasure for Secure Text-to-Image
        31777, -- 2405.16570 ID-to-3D: Expressive ID-guided 3D Heads via Score Distillation Samplin
        31811, -- 2405.16888 Part123: Part-aware 3D Reconstruction from a Single-view Image
        31845, -- 2405.17401 RB-Modulation: Training-Free Personalization of Diffusion Models using
        31855, -- 2405.17472 FreezeAsGuard: Mitigating Illegal Adaptation of Diffusion Models via S
        31859, -- 2405.17532 ClassDiffusion: More Aligned Personalization Tuning with Explicit Clas
        31881, -- 2405.17825 Diffusion Model Patching via Mixture-of-Prompts
        31896, -- 2405.17965 AttenCraft: Attention-guided Disentanglement of Multiple Concepts for
        31948, -- 2405.18424 3DitScene: Editing Any Scene via Language-guided Disentangled Gaussian
        32059, -- 2405.20032 Promptus: Can Prompts Streaming Replace Video Streaming with Stable Di
        32080, -- 2405.20271 ETHER: Efficient Finetuning of Large-Scale Models with Hyperplane Refl
        32108, -- 2405.20494 Slight Corruption in Pre-training Data Makes Better Diffusion Models
        32142, -- 2405.21050 Spectrum-Aware Parameter Efficient Fine-Tuning for Diffusion Models
        32164, -- 2406.00210 A-SDM: Accelerating Stable Diffusion through Model Assembly and Featur
        32194, -- 2406.00687 Lay-A-Scene: Personalized 3D Object Arrangement Using Text-to-Image Pr
        32335, -- 2406.02820 ORACLE: Leveraging Mutual Information for Consistent Character Generat
        32367, -- 2406.03215 Searching Priors Makes Text-to-Video Synthesis Better
        32483, -- 2406.04551 Improving Geo-diversity of Generated Images with Contextualized Vendi
        32526, -- 2406.05191 DiffusionPID: Interpreting Diffusion via Partial Information Decomposi
        32578, -- 2406.05871 OmniControlNet: Dual-stage Integration for Conditional Image Generatio
        32603, -- 2406.06133 ExtraNeRF: Visibility-Aware View Extrapolation of Neural Radiance Fiel
        32612, -- 2406.06258 Tuning-Free Visual Customization via View Iterative Self-Attention Con
        32631, -- 2406.06424 Margin-aware Preference Optimization for Aligning Diffusion Models wit
        32691, -- 2406.07209 MS-Diffusion: Multi-subject Zero-shot Image Personalization with Layou
        32734, -- 2406.07540 Ctrl-X: Controlling Structure and Appearance for Text-To-Image Generat
        32738, -- 2406.07547 Zero-shot Image Editing with Reference Imitation
        32813, -- 2406.08479 Real3D: Scaling Up Large Reconstruction Models with Real-World Images
        32841, -- 2406.08850 COVE: Unleashing the Diffusion Feature Correspondence for Consistent V
        32864, -- 2406.09162 EMMA: Your Text-to-Image Diffusion Model Can Secretly Accept Multi-Mod
        32875, -- 2406.09292 Neural Assets: 3D-Aware Multi-Object Scene Synthesis with Image Diffus
        32880, -- 2406.09305 Toffee: Efficient Million-Scale Dataset Construction for Subject-Drive
        32895, -- 2406.09400 Yo'LLaVA: Your Personalized Language and Vision Assistant
        32903, -- 2406.09413 Interpreting the Weight Space of Customized Diffusion Models
        32927, -- 2406.09750 ControlVAR: Exploring Controllable Visual Autoregressive Modeling
        33229, -- 2406.12292 JEN-1 DreamStyler: Customized Musical Concept Learning via Pivotal Par
        33351, -- 2406.13743 GenAI-Bench: Evaluating and Improving Compositional Text-to-Visual Gen
        33377, -- 2406.14130 ExVideo: Extending Video Diffusion Models via Parameter-Efficient Post
        33425, -- 2406.14599 Stylebreeder: Exploring and Democratizing Artistic Styles through Text
        33486, -- 2406.15331 Masked Extended Attention for Zero-Shot Virtual Try-On In The Wild
        33488, -- 2406.15339 Image Conductor: Precision Control for Interactive Video Synthesis
        33580, -- 2406.16537 Character-Adapter: Prompt-Guided Region Control for High-Fidelity Char
        33611, -- 2406.16855 DreamBench++: A Human-Aligned Benchmark for Personalized Image Generat
        33630, -- 2406.17236 LIPE: Learning Personalized Identity Prior for Non-rigid Image Editing
        33649, -- 2406.17396 SyncNoise: Geometrically Consistent Noise Prediction for Text-based 3D
        33683, -- 2406.17758 MotionBooth: Motion-Aware Customized Text-to-Video Generation
        33772, -- 2406.18893 AlignIT: Enhancing Prompt Alignment in Customization of Text-to-Image
        33778, -- 2406.18958 AnyControl: Create Your Artwork with Versatile Control on Text-to-Imag
        33862, -- 2406.20085 Auto Cherry-Picker: Learning from High-quality Generative Data Driven
        33965, -- 2407.01414 StyleShot: A Snapshot on Any Style
        34058, -- 2407.02489 Magic Insert: Style-Aware Drag-and-Drop
        34209, -- 2407.04604 PartCraft: Crafting Creative Objects by Parts
        34272, -- 2407.05546 AID-AppEAL: Automatic Image Dataset and Algorithm for Content Appeal E
        34274, -- 2407.05552 Ada-adapter:Fast Few-shot Style Personlization of Diffusion Model with
        34330, -- 2407.06187 JeDi: Joint-Image Diffusion Models for Finetuning-Free Personalized Te
        34352, -- 2407.06469 Sketch-Guided Scene Image Generation
        34367, -- 2407.06642 Powerful and Flexible: Personalized Text-to-Image Generation via Reinf
        34390, -- 2407.07077 ConceptExpress: Harnessing Diffusion Models for Single-image Unsupervi
        34397, -- 2407.07111 Diffusion Model-Based Video Editing: A Survey
        34400, -- 2407.07197 ColorPeel: Color Prompt Learning with Diffusion Models via Color and S
        34505, -- 2407.08674 Still-Moving: Customized Video Generation without Customized Video Dat
        34590, -- 2407.09779 Layout-and-Retouch: A Dual-stage Framework for Improving Diversity in
        34674, -- 2407.10910 DataDream: Few-shot Guided Dataset Generation
        34729, -- 2407.11433 CycleHOI: Improving Human-Object Interaction Detection with Cycle Cons
        34788, -- 2407.12164 Subject-driven Text-to-Image Generation via Preference-based Reinforce
        34930, -- 2407.13752 LogoSticker: Inserting Logos into Diffusion Models for Customized Gene
        34952, -- 2407.14078 Stable-Hair: Real-World Hair Transfer via Diffusion Model
        35042, -- 2407.15446 Text2Place: Affordance-aware Text Guided Human Placement
        35155, -- 2407.17365 ViPer: Visual Personalization of Generative Models via Individual Pref
        35174, -- 2407.17571 Diffusion Models For Multi-Modal Generative Modeling
        35304, -- 2407.20072 Generative Diffusion Model Bootstraps Zero-shot Classification of Feta
        35321, -- 2407.20455 Learning Feature-Preserving Portrait Editing from Generated Pairs
        35396, -- 2408.00001 Replication in Visual Diffusion Models: A Survey and Outlook
        35448, -- 2408.00735 TurboEdit: Text-Based Image Editing Using Few-Step Diffusion Models
        35532, -- 2408.02226 ProCreate, Don't Reproduce! Propulsive Energy Diffusion for Creative G
        35611, -- 2408.03355 FastEdit: Fast Text-Guided Single-Image Editing via Semantic-Aware Dif
        35699, -- 2408.05083 PreciseControl: Enhancing Text-To-Image Diffusion Models with Fine-Gra
        35719, -- 2408.05492 ZePo: Zero-Shot Portrait Stylization with Faster Sampling
        35741, -- 2408.05939 UniPortrait: A Unified Framework for Identity-Preserving Single- and M
        35788, -- 2408.06740 DiffLoRA: Generating Personalized Low-Rank Adaptation Weights with Dif
        35831, -- 2408.07433 MagicFace: Training-free Universal-Style Human Image Customized Synthe
        35957, -- 2408.09702 Photorealistic Object Insertion with Diffusion-Guided Inverse Renderin
        35959, -- 2408.09744 RealCustom++: Representing Images as Real-Word for Real-Time Customiza
        36086, -- 2408.11721 Detection-Driven Object Count Optimization for Text-to-Image Diffusion
        36180, -- 2408.13239 CustomCrafter: Customized Video Generation with Preserving Motion and
        36200, -- 2408.13674 GenCA: A Text-conditioned Generative Model for Realistic and Drivable
        36261, -- 2408.14765 CrossViewDiff: A Cross-View Diffusion Model for Satellite-to-Street Vi
        36267, -- 2408.14826 Alfie: Democratising RGBA Image Generation With No $$$
        36360, -- 2408.16266 Inversion Circle Interpolation: Diffusion-based Image Augmentation for
        36526, -- 2409.01835 Towards Generative Class Prompt Learning for Fine-grained Visual Recog
        36546, -- 2409.02097 LinFusion: 1 GPU, 1 Minute, 16K Image
        36629, -- 2409.03755 DC-Solver: Improving Predictor-Corrector Diffusion Sampler via Dynamic
        36661, -- 2409.04559 Thinking Outside the BBox: Unconstrained Generative Object Compositing
        36670, -- 2409.04847 Rethinking The Training And Evaluation of Rich-Context Layout-to-Image
        36697, -- 2409.05606 CustomContrast: A Multilevel Contrastive Perspective For Subject-Drive
        36815, -- 2409.08248 TextBoost: Towards One-Shot Personalization of Text-to-Image Models vi
        36833, -- 2409.08520 GroundingBooth: Grounding Text-to-Image Customization
        36894, -- 2409.09502 One missing piece in Vision and Language: A Survey on Comics Understan
        36901, -- 2409.09593 One-Shot Learning for Pose-Guided Person Image Synthesis in the Wild
        36999, -- 2409.11340 OmniGen: Unified Image Generation
        37020, -- 2409.11734 InverseMeetInsert: Robust Real Image Editing via Geometric Accumulatio
        37077, -- 2409.12576 StoryMaker: Towards Holistic Consistent Characters in Text-to-image Ge
        37120, -- 2409.13346 Imagine yourself: Tuning-Free Personalized Image Generation
        37180, -- 2409.14424 Dormant: Defending against Pose-driven Human Image Animation
        37210, -- 2409.14993 Multi-Modal Generative AI: Multi-modal LLM, Diffusion and Beyond
        37321, -- 2409.16949 DALDA: Data Augmentation Leveraging Diffusion Model and LLM with Adapt
        37325, -- 2409.17049 ControlCity: A Multimodal Diffusion Model Based Approach for Accurate
        37370, -- 2409.17740 AnyLogo: Symbiotic Subject-Driven Diffusion System with Gemini Status
        37382, -- 2409.17920 Resolving Multi-Condition Confusion for Finetuning-Free Personalized I
        37391, -- 2409.18071 FreeEdit: Mask-free Reference-based Image Editing with Multi-modal Ins
        37489, -- 2409.19624 Storynizor: Consistent Story Generation via Inter-Frame Synchronized a
        37521, -- 2409.19946 Illustrious: an Open Advanced Illustration Model
        37585, -- 2410.00398 CusConcept: Customized Visual Concept Decomposition with Diffusion Mod
        37590, -- 2410.00483 MCGM: Mask Conditional Text-to-Image Generative Model
        37636, -- 2410.01322 Forte : Finding Outliers with Representation Typicality Estimation
        37681, -- 2410.01731 ComfyGen: Prompt-Adaptive Workflows for Text-to-Image Generation
        37693, -- 2410.01801 FabricDiffusion: High-Fidelity Texture Transfer for 3D Garments Genera
        37716, -- 2410.02067 DisEnvisioner: Disentangled and Enriched Visual Prompt for Customized
        37791, -- 2410.02705 ControlAR: Controllable Image Generation with Autoregressive Models
        37983, -- 2410.04844 PostEdit: Posterior Sampling for Efficient Zero-Shot Image Editing
        37984, -- 2410.04891 Low-Rank Continual Personalization of Diffusion Models
        37985, -- 2410.04932 OmniBooth: Learning Latent Control for Image Synthesis with Multi-moda
        38015, -- 2410.05259 GS-VTON: Controllable 3D Virtual Try-on with Gaussian Splatting
        38040, -- 2410.05470 Image Watermarks are Removable Using Controllable Regeneration from Cl
        38053, -- 2410.05591 TweedieMix: Improving Multi-Concept Fusion for Diffusion-based Image/V
        38110, -- 2410.06244 Story-Adapter: A Training-free Iterative Framework for Long Story Visu
        38177, -- 2410.07113 Personalized Visual Instruction Tuning
        38231, -- 2410.07763 HARIVO: Harnessing Text-to-Image Models for Video Generation
        38235, -- 2410.07838 Minority-Focused Text-to-Image Generation via Prompt Optimization
        38272, -- 2410.08192 HybridBooth: Hybrid Prompt Inversion for Efficient Subject-Driven Gene
        38353, -- 2410.09382 CLIP-SCGI: Synthesized Caption-Guided Inversion for Person Re-Identifi
        38387, -- 2410.09802 EBDM: Exemplar-guided Image Translation with Brownian-bridge Diffusion
        38403, -- 2410.10058 Learning to Customize Text-to-Image Diffusion In Diverse Context
        38411, -- 2410.10133 TextCtrl: Diffusion-based Scene Text Editing with Prior Guidance Contr
        38415, -- 2410.10207 MagicEraser: Erasing Any Objects via Semantics-Aware Control
        38514, -- 2410.11208 DreamSteerer: Enhancing Source Image Conditioned Editability using Per
        38560, -- 2410.11815 SGEdit: Bridging LLM with Text2Image Generative Model for Scene Graph-
        38594, -- 2410.12312 FaceChain-FACT: Face Adapter with Decoupled Training for Identity-pres
        38701, -- 2410.13360 RAP: Retrieval-Augmented Personalization for Multimodal Large Language
        38702, -- 2410.13370 MagicTailor: Component-Controllable Personalization in Text-to-Image D
        38718, -- 2410.13618 LoLDU: Low-Rank Adaptation via Lower-Diag-Upper Decomposition for Para
        38750, -- 2410.13830 DreamVideo-2: Zero-Shot Subject-Driven Video Customization with Precis
        38803, -- 2410.14429 FashionR2R: Texture-preserving Rendered-to-Real Image Translation with
        38847, -- 2410.14987 SeaS: Few-shot Industrial Anomaly Image Generation with Separation and
        38851, -- 2410.15027 Group Diffusion Transformers are Unsupervised Multitask Learners
        38889, -- 2410.15618 Erasing Undesirable Concepts in Diffusion Models with Adversarial Pres
        38984, -- 2410.16770 The Scene Language: Representing Scenes with Programs, Words, and Embe
        38985, -- 2410.16794 One-Step Diffusion Distillation through Score Implicit Matching
        39036, -- 2410.17594 How to Continually Adapt Text-to-Image Diffusion Models for Flexible C
        39127, -- 2410.18756 Schedule Your Edit: A Simple yet Effective Diffusion Noise Schedule fo
        39133, -- 2410.18823 Towards Visual Text Design Transfer Across Languages
        39149, -- 2410.18975 Unbounded: A Generative Infinite Game of Character Life Simulation
        39379, -- 2410.22901 HelloMeme: Integrating Spatial Knitting Attentions to Embed High-Level
        39407, -- 2410.23280 RelationBooth: Towards Relation-Aware Customized Object Generation
        39458, -- 2410.24151 Scaling Concept With Text-Guided Diffusion Models
        39498, -- 2411.00399 StyleTex: Style Image-Guided Texture Generation for 3D Models
        39693, -- 2411.03982 ReEdit: Multimodal Exemplar-Based Image Editing with Diffusion Models
        39762, -- 2411.05003 ReCapture: Generative Video Camera Controls for User-Provided Videos u
        39877, -- 2411.07126 Edify Image: High-Quality Image Generation with Pixel Space Laplacian
        39889, -- 2411.07199 OmniEdit: Building Image Editing Generalist Models Through Specialist
        39892, -- 2411.07232 Add-it: Training-Free Object Insertion in Images With Pretrained Diffu
        40004, -- 2411.09449 Image Regeneration: Evaluating Text-to-Image Model via Generating Iden
        40179, -- 2411.12872 From Text to Pose to Image: Improving Diffusion Model Control and Qual
        40230, -- 2411.13632 ID-Patch: Robust ID Association for Group Photo Personalization
        40278, -- 2411.14517 The Double-Ellipsoid Geometry of CLIP
        40319, -- 2411.15098 OminiControl: Minimal and Universal Control for Diffusion Transformer
        40338, -- 2411.15245 AnyText2: Visual Text Generation and Editing With Customizable Attribu
        40340, -- 2411.15260 VIVID-10M: A Dataset and Baseline for Versatile and Interactive Video
        40343, -- 2411.15277 Foundation Cures Personalization: Recovering Facial Personalized Model
        40360, -- 2411.15466 Large-Scale Text-to-Image Model with Inpainting is a Zero-Shot Subject
        40446, -- 2411.16657 DreamRunner: Fine-Grained Storytelling Video Generation with Retrieval
        40479, -- 2411.16969 ZoomLDM: Latent Diffusion Model for multi-scale image generation
        40484, -- 2411.17048 PersonalVideo: High ID-Fidelity Video Customization without Dynamic an
        40497, -- 2411.17223 DreamMix: Decoupling Object Attributes for Enhanced Editability in Cus
        40513, -- 2411.17440 Identity-Preserving Text-to-Video Generation by Frequency Decompositio
        40551, -- 2411.17786 DreamCache: Finetuning-Free Lightweight Personalized Image Generation
        40588, -- 2411.18281 MotionCharacter: Identity-Preserving and Motion Controllable Human Vid
        40613, -- 2411.18616 Diffusion Self-Distillation for Zero-Shot Customized Image Generation
        40622, -- 2411.18665 SpotLight: Shadow-Guided Object Relighting via Diffusion
        40675, -- 2411.19390 DreamBlend: Advancing Personalized Fine-tuning of Text-to-Image Diffus
        40740, -- 2412.00136 FonTS: Text Rendering with Typography and Style Controls
        40746, -- 2412.00176 Opt-In Art: Learning Art Styles Only from Few Examples
        40817, -- 2412.01223 PainterNet: Adaptive Image Inpainting with Actual-Token Attention and
        40820, -- 2412.01254 EmojiDiff: Advanced Facial Expression Control with High Identity Prese
        40834, -- 2412.01485 SerialGen: Personalized Image Generation by First Standardization Then
        40884, -- 2412.02168 Generative Photography: Scene-Consistent Camera Control for Realistic
        40940, -- 2412.02912 ShapeWords: Guiding Text-to-Image Synthesis with 3D Shape-Aware Prompt
        40962, -- 2412.03177 PatchDPO: Patch-level DPO for Finetuning-free Personalized Image Gener
        40974, -- 2412.03347 DIVE: Taming DINO for Subject-Driven Video Editing
        41006, -- 2412.03632 MV-Adapter: Multi-view Consistent Image Generation Made Easy
        41019, -- 2412.03812 Pinco: Position-induced Consistent Adapter for Diffusion Transformer i
        41042, -- 2412.04146 AnyDressing: Customizable Multi-Garment Virtual Dressing via Latent Di
        41083, -- 2412.04465 UnZipLoRA: Separating Content and Style from a Single Image
        41136, -- 2412.05101 The Silent Prompt: Initial Noise as Implicit Guidance for Goal-Driven
        41139, -- 2412.05148 LoRA.rar: Learning to Merge LoRAs via Hypernetworks for Subject-Style
        41155, -- 2412.05278 Birth and Death of a Rose
        41253, -- 2412.06774 Visual Lexicon: Rich Image Features in Language Space
        41308, -- 2412.07589 DiffSensei: Bridging Multi-Modal LLMs and Diffusion Models for Customi
        41324, -- 2412.07744 StyleMaster: Stylize Your Video with Artistic Generation and Translati
        41326, -- 2412.07750 Multi-Shot Character Consistency for Text-to-Video Generation
        41342, -- 2412.07776 Video Motion Transfer with Diffusion Transformers
        41386, -- 2412.08503 StyleStudio: Text-Driven Style Transfer with Selective Control of Styl
        41407, -- 2412.08645 ObjectMate: A Recurrence Prior for Object Insertion and Subject-Driven
        41431, -- 2412.09013 Arbitrary-steps Image Super-resolution via Diffusion Inversion
        41441, -- 2412.09169 DECOR:Decomposition and Projection of Text Embeddings for Text-to-Imag
        41486, -- 2412.09614 Context Canvas: Enhancing Text-to-Image Diffusion Models with Knowledg
        41492, -- 2412.09622 LoRACLR: Contrastive Adaptation for Customization of Diffusion Models
        41498, -- 2412.09694 Omni-ID: Holistic Identity Representation Designed for Generative Task
        41514, -- 2412.09910 Prompt2Perturb (P2P): Text-Guided Diffusion-Based Adversarial Attacks
        41595, -- 2412.11058 SHMT: Self-supervised Hierarchical Makeup Transfer via Latent Diffusio
        41616, -- 2412.11423 Nearly Zero-Cost Protection Against Mimicry by Personalized Diffusion
        41656, -- 2412.11767 IDEA-Bench: How Far are Generative Models from Professional Designing?
        41661, -- 2412.11815 ColorFlow: Retrieval-Augmented Image Sequence Colorization
        41709, -- 2412.12242 OmniPrism: Learning Disentangled Visual Concept for Image Generation
        41810, -- 2412.13565 CA-Edit: Causality-Aware Condition Adapter for High-Fidelity Local Fac
        41853, -- 2412.14168 FashionComposer: Compositional Fashion Image Generation
        41875, -- 2412.14462 Affordance-Aware Object Insertion via Mask-Aware Dual Diffusion
        41933, -- 2412.15216 UIP2P: Unsupervised Instruction-based Image Editing via Cycle Edit Con
        42000, -- 2412.16156 Personalized Representation from Personalized Generation
        42100, -- 2412.17610 Personalized Large Vision-Language Models
        42203, -- 2412.18945 Single Trajectory Distillation for Accelerating Image and Video Style
        42254, -- 2412.19853 Conditional Balance: Improving Multi-Conditioning Trade-Offs in Image
        42424, -- 2501.01371 CLIP-UP: CLIP-Based Unanswerable Problem Detection for Visual Question
        42426, -- 2501.01407 Nested Attention: Semantic-aware Attention Values for Concept Personal
        42452, -- 2501.01790 Ingredients: Blending Custom Photos with Video Diffusion Transformers
        42582, -- 2501.03931 Magic Mirror: ID-Preserved Video Generation in Video Diffusion Transfo
        42596, -- 2501.04144 Chirpy3D: Creative Fine-grained 3D Object Fabrication via Part Samplin
        42633, -- 2501.04698 ConceptMaster: Multi-Concept Video Customization on Diffusion Transfor
        42634, -- 2501.04699 EditAR: Unified Conditional Generation with Autoregressive Models
        42635, -- 2501.04765 TREAD: Token Routing for Efficient Architecture-agnostic Diffusion Tra
        42668, -- 2501.05379 Arc2Avatar: Generating Expressive 3D Avatars from a Single Image via I
        42693, -- 2501.05710 EmotiCrafter: Text-to-Emotional-Image Generation based on Valence-Arou
        42721, -- 2501.06187 Multi-subject Open-set Personalization in Video Generation
        42739, -- 2501.06438 Qffusion: Controllable Portrait Video Editing via Quadrant-Grid Attent
        42760, -- 2501.06751 Padding Tone: A Mechanistic Analysis of Padding Tokens in T2I Models
        42802, -- 2501.07530 IP-FaceDiff: Identity-Preserving Facial Video Editing with Diffusion
        42849, -- 2501.08332 MangaNinja: Line Art Colorization with Precise Reference Following
        42850, -- 2501.08333 DAViD: Modeling Dynamic Affordance of 3D Objects using Pre-trained Vid
        42852, -- 2501.08347 SCOT: Self-Supervised Contrastive Pretraining For Zero-Shot Compositio
        42870, -- 2501.08727 Transformed Low-rank Adaptation via Tensor Decomposition and Its Appli
        42913, -- 2501.09503 AnyStory: Towards Unified Single and Multiple Subject Personalization
        42932, -- 2501.09756 SynthLight: Portrait Relighting with Diffusion Model by Learning to Re
        43059, -- 2501.12173 ComposeAnyone: Controllable Layout-to-Human Generation with Decoupled
        43063, -- 2501.12224 TokenVerse: Versatile Multi-concept Personalization in Token Modulatio
        43089, -- 2501.12612 T2ISafety: Benchmark for Assessing Fairness, Toxicity, and Privacy in
        43162, -- 2501.13787 Parameter-Efficient Fine-Tuning for Foundation Models
        43195, -- 2501.14316 PAID: A Framework of Product-Centric Advertising Image Design
        43257, -- 2501.15407 Turn That Frown Upside Down: FaceID Customization via Cross-Training D
        43278, -- 2501.15641 IP-Prompter: Training-Free Theme-Specific Image Generation via Dynamic
        43602, -- 2502.01720 Generating Multi-Image Synthetic Data for Text-to-Image Customization
        43655, -- 2502.02465 Towards Consistent and Controllable Image Synthesis for Face Editing
        43659, -- 2502.02492 VideoJAM: Joint Appearance-Motion Representations for Enhanced Motion
        43744, -- 2502.04050 PartEdit: Fine-Grained Image Editing using Pre-Trained Diffusion Model
        43756, -- 2502.04263 Cross the Gap: Exposing the Intra-modal Misalignment in CLIP via Modal
        43794, -- 2502.04475 Augmented Conditioning Is Enough For Effective Training Image Generati
        43841, -- 2502.05153 Hummingbird: High Fidelity Image Generation via Multimodal Context Ali
        43934, -- 2502.06527 CustomVideoX: 3D Reference Attention Driven Dynamic Adaptation for Zer
        43949, -- 2502.06734 Señorita-2M: A High-Quality Instruction-based Dataset for General Vide
        44003, -- 2502.07215 PDV: Prompt Directional Vectors for Zero-shot Composed Image Retrieval
        44142, -- 2502.09164 E-MD3C: Taming Masked Diffusion Transformers for Efficient Zero-Shot O
        44150, -- 2502.09411 ImageRAG: Dynamic Image Retrieval for Reference-Guided Image Generatio
        44225, -- 2502.10458 I Think, Therefore I Diffuse: Enabling Multimodal In-Context Reasoning
        44273, -- 2502.11079 Phantom: Subject-consistent video generation via cross-modal alignment
        44511, -- 2502.13081 Personalized Image Generation with Deep Generative Models: A Decade Su
        44644, -- 2502.14397 PhotoDoodle: Learning Artistic Image Editing from Few-Shot Pairwise Da
        44698, -- 2502.14844 Dynamic Concepts Personalization from Single Videos
        44742, -- 2502.15203 FlipConcept: Tuning-Free Multi-Concept Personalization for Text-to-Ima
        44947, -- 2502.17435 GCC: Generative Color Constancy via Diffusing a Color Checker
        45027, -- 2502.18477 Recommendations Beyond Catalogs: Diffusion Models for Personalized Gen
        45030, -- 2502.18495 A Comprehensive Survey on Composed Image Retrieval
        45112, -- 2502.19673 SubZero: Composing Subject, Style, and Action via Zero-Shot Personaliz
        45156, -- 2502.20172 Multimodal Representation Alignment for Image Generation: Text-Image I
        45160, -- 2502.20235 Attention Distillation: A Unified Approach to Visual Characteristics T
        45247, -- 2503.00276 Learning to Animate Images from A Few Videos to Portray Delicate Human
        45418, -- 2503.02537 RectifiedHR: Enable Efficient High-Resolution Image Generation via Ene
        45495, -- 2503.03651 DoraCycle: Domain-Oriented Adaptation of Unified Generative Model in M
        45601, -- 2503.05204 Data-Efficient Generalization for Zero-shot Composed Image Retrieval
        45698, -- 2503.06505 DynamicID: Zero-Shot Multi-ID Image Personalization with Flexible Faci
        45709, -- 2503.06568 Conceptrol: Concept Control of Zero-shot Personalized Image Generation
        45741, -- 2503.06956 LatexBlend: Scaling Multi-concept Customized Generation with Latent Te
        45750, -- 2503.07027 EasyControl: Adding Efficient and Flexible Control for Diffusion Trans
        45758, -- 2503.07091 FaceID-6M: A Large-Scale, Open-Source FaceID Customization Dataset
        45788, -- 2503.07392 SPEED: Scalable, Precise, and Efficient Concept Erasure for Diffusion
        45814, -- 2503.07602 DreamRelation: Relation-Centric Video Customization
        45879, -- 2503.08478 NullFace: Training-Free Localized Face Anonymization
        45937, -- 2503.09130 InteractEdit: Zero-Shot Editing of Human-Object Interactions in Images
        45944, -- 2503.09277 UniCombine: Unified Multi-Conditional Combination with Diffusion Trans
        45956, -- 2503.09368 PerCoV2: Improved Ultra-Low Bit-Rate Perceptual Image Compression with
        45994, -- 2503.09669 Silent Branding Attack: Trigger-free Data Poisoning Attack on Text-to-
        46013, -- 2503.10037 Investigating and Improving Counter-Stereotypical Action Relation in T
        46018, -- 2503.10125 Proxy-Tuning: Tailoring Multimodal Autoregressive Models for Subject-D
        46038, -- 2503.10342 DreamInsert: Zero-Shot Image-to-Video Object Insertion from A Single I
        46042, -- 2503.10365 Piece it Together: Part-Based Concepting with IP-Priors
        46047, -- 2503.10406 RealGeneral: Unifying Visual Generation via Temporal In-Context Learni
        46066, -- 2503.10614 ConsisLoRA: Enhancing Content and Style Consistency for LoRA-based Sty
        46083, -- 2503.10637 Distilling Diversity and Control in Diffusion Models
        46174, -- 2503.11937 Att-Adapter: A Robust and Precise Domain-Specific Multi-Attributes T2I
        46186, -- 2503.12271 Reflect-DiT: Inference-Time Scaling for Text-to-Image Diffusion Transf
        46208, -- 2503.12590 Personalize Anything for Free with Diffusion Transformer
        46213, -- 2503.12689 MagicID: Hybrid Preference Optimization for ID-Consistent and Dynamic-
        46267, -- 2503.13434 BlobCtrl: A Unified and Flexible Framework for Element-level Image Gen
        46322, -- 2503.14275 Free-Lunch Color-Texture Disentanglement for Stylized Image Generation
        46363, -- 2503.14830 Decompositional Neural Scene Reconstruction with Generative Diffusion
        46446, -- 2503.16025 Single Image Iterative Subject-driven Generation and Editing
        46488, -- 2503.16418 InfiniteYou: Flexible Photo Recrafting While Preserving Your Identity
        46528, -- 2503.16948 MagicColor: Multi-Instance Sketch Colorization
        46532, -- 2503.16983 Enabling Versatile Controls for Video Diffusion Models
        46535, -- 2503.17069 PVChat: Personalized Video Chat with One-Shot Learning
        46855, -- 2503.21541 LOCATEdit: Graph Laplacian Optimized Cross Attention for Localized Tex
        46885, -- 2503.21781 VideoMage: Multi-Subject and Motion Customization of Text-to-Video Dif
        47012, -- 2503.23402 Diffusion Meets Few-shot Class Incremental Learning
        47077, -- 2503.24387 Consistent Subject Generation via Contrastive Instantiated Concepts
        47081, -- 2504.00010 LayerCraft: Enhancing Text-to-Image Generation with CoT Reasoning and
        47202, -- 2504.02154 FreSca: Unveiling the Scaling Space in Diffusion Models
        47203, -- 2504.02160 Less-to-More Generalization: Unlocking More Controllability by In-Cont
        47207, -- 2504.02231 AC-LoRA: Auto Component LoRA for Personalized Artistic Style Image Gen
        47224, -- 2504.02436 SkyReels-A2: Compose Anything in Video Diffusion Transformers
        47239, -- 2504.02612 Fine-Tuning Visual Autoregressive Models for Subject-Driven Generation
        47283, -- 2504.03292 FaR: Enhancing Multi-Concept Text-to-Image Diffusion via Concept Fusio
        47430, -- 2504.06256 Transfer between Modalities with MetaQueries
        47455, -- 2504.07046 A Unified Agentic Framework for Evaluating Conditional Image Generatio
        47482, -- 2504.07405 FlexIP: Dynamic Control of Preservation and Personality for Customized
        47536, -- 2504.08111 POEM: Precise Object-level Editing via MLLM control
        47752, -- 2504.11478 Flux Already Knows -- Activating Subject-Driven Image Generation witho
        47791, -- 2504.12240 Cobra: Efficient Line Art COlorization with BRoAder References
        47811, -- 2504.12395 InstantCharacter: Personalize Any Characters with a Scalable Diffusion
        47839, -- 2504.12782 Set You Straight: Auto-Steering Denoising Trajectories to Sidestep Unw
        47870, -- 2504.13162 Personalized Text-to-Image Generation with Auto-Regressive Models
        47927, -- 2504.14202 Learning Joint ID-Textual Representation for ID-Preserving Image Synth
        47929, -- 2504.14219 PRISM: A Unified Framework for Photorealistic Reconstruction and Intri
        48047, -- 2504.15958 FreeGraftor: Training-Free Cross-Image Feature Grafting for Subject-Dr
        48089, -- 2504.16915 DreamO: A Unified Framework for Image Customization
        48104, -- 2504.17253 DIVE: Inverting Conditional Diffusion Models for Discriminative Tasks
        48111, -- 2504.17502 RefVNLI: Towards Scalable Evaluation of Subject-driven Text-to-image G
        48123, -- 2504.17816 Subject-driven Video Generation via Disentangled Identity and Motion
        48193, -- 2504.19724 RepText: Rendering Visual Text via Replicating
        48244, -- 2504.20998 YoChameleon: Personalized Vision and Language Generation
        48328, -- 2505.01104 VSC: Visual Search Compositional Text-to-Image Diffusion Model
        48415, -- 2505.02823 MUSAR: Exploring Multi-Subject Customization from Single-Subject Datas
        48433, -- 2505.03097 Not All Parameters Matter: Masking Diffusion Models for Enhancing Gene
        48459, -- 2505.03730 FlexiAct: Towards Flexible Action Control in Heterogeneous Scenarios
        48489, -- 2505.04512 HunyuanCustom: A Multimodal-Driven Architecture for Customized Video G
        48613, -- 2505.06985 BridgeIV: Bridging Customized Image and Video Generation through Test-
        48644, -- 2505.07652 ShotAdapter: Text-to-Multi-Shot Video Generation with Diffusion Models
        48716, -- 2505.09263 Few-Shot Anomaly-Driven Generation for Anomaly Classification and Segm
        48784, -- 2505.10558 Style Customization of Text-to-Vector Generation with Image Diffusion
        48847, -- 2505.11245 Diffusion-NPO: Negative Preference Optimization for Better Preference
        49066, -- 2505.13437 FinePhys: Fine-grained Human Action Generation by Explicitly Incorpora
        49562, -- 2505.17908 ComfyMind: Toward General-Purpose Generation via Tree-Based Planning a
        49671, -- 2505.18985 STRICT: Stress Test of Rendering Images Containing Text
        49729, -- 2505.19415 MMIG-Bench: Towards Comprehensive and Explainable Evaluation of Multi-
        49847, -- 2505.20271 In-Context Brush: Zero-shot Customized Subject Insertion with Context-
        49861, -- 2505.20292 OpenS2V-Nexus: A Detailed Benchmark and Million-Scale Dataset for Subj
        49912, -- 2505.20914 Geometry-Editable and Appearance-Preserving Object Compositon
        50000, -- 2505.22129 What Makes for Text to 360-degree Panorama Generation with Stable Diff
        50099, -- 2505.23325 Dimension-Reduction Attack! Video Generative Models are Experts on Con
        50154, -- 2505.23758 LoRAShop: Training-Free Multi-Concept Image Generation and Editing wit
        50365, -- 2506.01144 FlowMo: Variance-Based Flow Guidance for Coherent Motion in Video Gene
        50463, -- 2506.02620 FlexPainter: Flexible and Multi-View Consistent Texture Generation
        50529, -- 2506.03621 Negative-Guided Subject Fidelity Optimization for Zero-Shot Subject-Dr
        50838, -- 2506.08257 Highly Compressed Tokenizer Can Generate Without Training
        50953, -- 2506.09916 Only-Style: Stylistic Consistency in Image Generation without Content
        51014, -- 2506.10540 AniMaker: Automated Multi-Agent Animated Storytelling with MCTS-Driven
        51379, -- 2506.18729 MuseControlLite: Multifunctional Music Generation with Lightweight Con
        51411, -- 2506.19360 SoK: Can Synthetic Images Replace Real Data? A Survey of Utility and P
        51503, -- 2506.21272 FairyGen: Storied Cartoon Video from a Single Child-Drawn Character
        51513, -- 2506.21416 XVerse: Consistent Multi-Subject Control of Identity and Semantic Attr
        51704, -- 2507.04584 S$^2$Edit: Text-Guided Image Editing with Precise Semantic and Spatial
        51753, -- 2507.05964 T-LoRA: Single Image Diffusion Model Customization Without Overfitting
        51761, -- 2507.06146 Prompt-Free Conditional Diffusion for Multi-object Image Augmentation
        51839, -- 2507.08396 Subject-Consistent and Pose-Diverse Text-to-Image Generation
        51902, -- 2507.11441 Implementing Adaptations for Vision AutoRegressive Model
        51908, -- 2507.11533 CharaConsist: Fine-Grained Consistent Character Generation
        51921, -- 2507.12142 RiemannLoRA: A Unified Riemannian Framework for Ambiguity-Free LoRA Op
        51975, -- 2507.13984 CSD-VAR: Content-Style Decomposition in Visual Autoregressive Models
        52065, -- 2507.19058 ScenePainter: Semantically Consistent Perpetual 3D Scene Generation wi
        52086, -- 2507.20976 Adapting Vehicle Detectors for Aerial Imagery to Unseen Domains with W
        52249, -- 2508.04825 Voost: A Unified and Scalable Diffusion Transformer for Bidirectional
        52308, -- 2508.07901 Stand-In: A Lightweight and Plug-and-Play Identity Control for Video G
        52321, -- 2508.08244 Cut2Next: Generating Next Shot via In-Context Tuning
        52424, -- 2508.13632 OmniTry: Virtual Try-On Anything without Masks
        52479, -- 2508.16577 MV-RAG: Retrieval Augmented Multiview Diffusion
        52529, -- 2508.18966 USO: Unified Style and Subject-Driven Generation via Disentangled and
        52540, -- 2508.19247 VoxHammer: Training-Free Precise and Coherent 3D Editing in Native 3D
        52691, -- 2509.06818 UMO: Scaling Multi-Identity Consistency for Image Customization via Ma
        52804, -- 2509.21278 Does FLUX Already Know How to Perform Physically Plausible Image Compo
        52879, -- 2509.15496 Lynx: Towards High-Fidelity Personalized Video Generation
        52958, -- 2509.21679 ReviewScore: Misinformed Peer Review Detection with Large Language Mod
        52969, -- 2509.21989 Mind-the-Glitch: Visual Correspondence for Detecting Inconsistencies i
        53046, -- 2509.21953 MultiCrafter: High-Fidelity Multi-Subject Generation via Spatially Dis
        53237, -- 2510.04290 ChronoEdit: Towards Temporal Reasoning for Image Editing and World Sim
        53372, -- 2510.08143 UniMMVSR: A Unified Multi-Modal Framework for Cascaded Video Super-Res
        53387, -- 2510.06679 DreamOmni2: Multimodal Instruction-based Editing and Generation
        53390, -- 2509.24817 UP2You: Fast Reconstruction of Yourself from Unconstrained Photo Colle
        53449, -- 2510.07656 MONKEY: Masking ON KEY-Value Activation Adapter for Personalization
        53497, -- 2510.09474 Multimodal Policy Internalization for Conversational Agents
        53618, -- 2510.14978 Learning an Image Editing Model without Image Editing Pairs
        53649, -- 2510.15868 LightsOut: Diffusion-based Outpainting for Enhanced Lens Flare Removal
        53794, -- 2510.20820 LayerComposer: Interactive Personalized T2I via Spatially-Aware Layere
        53862, -- 2510.20512 EchoDistill: Bidirectional Concept Distillation for One-Step Diffusion
        53865, -- 2510.23605 Track, Inpaint, Resplat: Subject-driven 3D and 4D Generation with Prog
        53882, -- 2510.24657 Group Relative Attention Guidance for Image Editing
        53961, -- 2510.15510 Exploring Conditions for Diffusion models in Robotic Control
        54008, -- 2510.24078 Beyond Objects: Contextual Synthetic Data Generation for Fine-Grained
        54243, -- 2511.10555 A Style is Worth One Code: Unlocking Code-to-Style Image Generation wi
        54403, -- 2511.21691 Canvas-to-Image: Compositional Image Generation with Multimodal Contro
        54448, -- 2511.20614 The Consistency Critic: Correcting Inconsistencies in Generated Images
        54463, -- 2511.22989 MultiBanana: A Challenging Benchmark for Multi-Reference Text-to-Image
        54480, -- 2512.01686 DreamingComics: A Story Visualization Pipeline via Subject and Layout
        54524, -- 2512.03013 In-Context Sync-LoRA for Portrait Video Editing
        54594, -- 2512.03683 GaussianBlender: Instant Stylization of 3D Gaussians with Disentangled
        54643, -- 2512.08294 OpenSubject: Leveraging Video-Derived Identity and Diversity Priors fo
        54686, -- 2512.09824 Composing Concepts from Images and Videos via Concept-prompt Binding
        54722, -- 2512.10955 Omni-Attribute: Open-vocabulary Attribute Encoder for Visual Concept P
        54870, -- 2512.16625 DeContext as Defense: Safe Image Editing in Diffusion Transformers
        54943, -- 2512.19661 Over++: Generative Video Compositing for Layer Interaction Effects
        55034, -- 2512.22984 Reverse Personalization
        55036, -- 2512.22525 DreamOmni3: Scribble-based Editing and Generation
        55108, -- 2512.22877 M-ErasureBench: A Comprehensive Multimodal Evaluation Benchmark for Co
        55121, -- 2601.03256 Muses: Designing, Composing, Generating Nonexistent Fantasy 3D Creatur
        55171, -- 2601.05124 Re-Align: Structured Reasoning-guided Alignment for In-Context Image G
        55323, -- 2601.10714 Alterbute: Editing Intrinsic Attributes of Objects in Images
        55652, -- 2601.22680 Visual Personalization Turing Test
        55680, -- 2602.01335 Beyond Pixels: Visual Metaphor Transfer via Schema-Driven Agentic Reas
        56225, -- 2602.15727 Spanning the Visual Analogy Space with a Weight Basis of LoRAs
        56556, -- 2603.07561 PureCC: Pure Learning for Text-to-Image Concept Customization
        56567, -- 2603.07236 HY-WU (Part I): An Extensible Functional Neural Memory Framework and A
        56606, -- 2603.02816 BrandFusion: A Multi-Agent Framework for Seamless Brand Integration in
        56625, -- 2603.10256 ID-LoRA: Identity-Driven Audio-Video Personalization with In-Context L
        56763, -- 2603.12743 MoKus: Leveraging Cross-Modal Knowledge Transfer for Knowledge-Aware C
        56857, -- 2603.18524 3DreamBooth: High-Fidelity 3D Subject-Driven Video Generation Model
        56898, -- 2603.19708 WorldAgents: Can Foundation Image Models be Agents for 3D World Models
        56954, -- 2603.21884 Not All Layers Are Created Equal: Adaptive LoRA Ranks for Personalized
        57134, -- 2603.27520 TokenDial: Continuous Attribute Control in Text-to-Video via Spatiotem
        57242, -- 2604.04911 SpatialEdit: Benchmarking Fine-Grained Image Spatial Editing
        57335, -- 2604.08364 MegaStyle: Constructing Diverse and Scalable Style Dataset via Consist
        57366, -- 2604.08536 RewardFlow: Generate Images by Optimizing What You Reward
        57371, -- 2604.07427 Personalizing Text-to-Image Generation to Individual Taste
        57793, -- 2604.24351 Diffusion Templates: A Unified Plugin Framework for Controllable Diffu
        58159, -- 2604.14591 Prompt-Guided Image Editing with Masked Logit Nudging in Visual Autore
        58215, -- 2604.12575 StructDiff: A Structure-Preserving and Spatially Controllable Diffusio
        58360, -- 2604.08915 Large-Scale Universal Defect Generation: Foundation Models and Dataset
        58739, -- 2602.01639 ReCALL: Recalibrating Capability Degradation for MLLM-based Composed I
        58764, -- 2603.28493 ConceptWeaver: Weaving Disentangled Concepts with Flow
        59052, -- 2603.21045 LPNSR: Prior-Enhanced Diffusion Image Super-Resolution via LR-Guided N
        59094, -- 2603.20012 Diffusion-Based Makeup Transfer with Facial Region-Aware Makeup Featur
        59097, -- 2603.19862 IsoCLIP: Decomposing CLIP Projectors for Efficient Intra-modal Alignme
        59457, -- 2603.12930 Rethinking VLMs for Image Forgery Detection and Localization
        59608, -- 2602.14552 OmniVTON++: Training-Free Universal Virtual Try-On with Principal Pose
        60057, -- 2602.23697 Towards Source-Aware Object Swapping with Initial Noise Perturbation
        60243, -- 2602.22510 Pix2Key: Controllable Open-Vocabulary Retrieval with Semantic Decompos
        60265, -- 2602.22197 Off-The-Shelf Image-to-Image Models Are All You Need To Defeat Image P
        60309, -- 2602.21402 FlowFixer: Towards Detail-Preserving Subject-Driven Generation
        60370, -- 2602.19976 SongEcho: Towards Cover Song Generation via Instance-Adaptive Element-
        60390, -- 2602.19575 ConceptPrism: Concept Disentanglement in Personalized Diffusion Models
        60984, -- 2602.08615 Inspiration Seeds: Learning Non-Literal Visual Combinations for Genera
        61357, -- 2602.03220 PokeFusion Attention: Enhancing Reference-Free Style-Conditioned Gener
        61531, -- 2602.01306 DeCorStory: Gram-Schmidt Prompt Embedding Decorrelation for Consistent
        61583, -- 2602.00924 Supervised sparse auto-encoders as unconstrained feature models for se
        61779, -- 2601.22094 RefAny3D: 3D Asset-Referenced Diffusion Models for Image Generation
        61923, -- 2601.20246 BLENDER: Blended Text Embeddings and Diffusion Residuals for Intra-Cla
        62672, -- 2601.06965 Unified Personalized Understanding, Generating and Editing
        62698, -- 2601.06605 Sissi: Zero-shot Style-guided Image Synthesis via Semantic-style Integ
        62770, -- 2601.05127 LooseRoPE: Content-aware Attention Manipulation for Semantic Harmoniza
        62942, -- 2601.02987 LAMS-Edit: Latent and Attention Mixing with Schedulers for Improved Co
        63219, -- 2512.23537 AnyMS: Bottom-up Attention Decoupling for Layout-guided and Training-f
        63234, -- 2512.23245 ASemConsist: Adaptive Semantic Feature Control for Training-Free Ident
        63757, -- 2512.12375 V-Warper: Appearance-Consistent Video Diffusion Personalization via Va
        63772, -- 2512.12193 SMRABooth: Subject and Motion Representation Alignment for Customized
        63783, -- 2512.11763 Reducing Domain Gap with Diffusion-Based Domain Adaptation for Cell Co
        63938, -- 2512.08477 ContextDrag: Precise Drag-Based Image Editing via Context-Preserving T
        64156, -- 2512.03964 Training for Identity, Inference for Controllability: A Unified Approa
        64256, -- 2512.01895 StyleYourSmile: Cross-Domain Face Retargeting Without Paired Multi-Sty
        64308, -- 2512.01236 PSR: Scaling Multi-Subject Personalized Image Generation with Pairwise
        64371, -- 2512.00343 Assimilation Matters: Model-level Backdoor Detection in Vision-Languag
        64481, -- 2511.21216 AuthenLoRA: Entangling Stylization with Imperceptible Watermarks for C
        64520, -- 2511.20629 MapReduce LoRA: Advancing the Pareto Front in Multi-Preference Optimiz
        64562, -- 2511.19965 HiCoGen: Hierarchical Compositional Text-to-Image Generation in Diffus
        64580, -- 2511.19811 Training-Free Generation of Diverse and High-Fidelity Images via Promp
        64636, -- 2511.18775 Rethinking Garment Conditioning in Diffusion-based Virtual Try-On
        64688, -- 2511.18281 Uni-DAD: Unified Distillation and Adaptation of Diffusion Models for F
        64705, -- 2511.17979 FeRA: Frequency-Energy Constrained Routing for Effective Diffusion Ada
        64766, -- 2511.16666 SceneDesigner: Controllable Multi-Object Image Generation with 9-DoF P
        65398, -- 2511.03156 Finetuning-Free Personalization of Text to Image Generation via Hypern
        65541, -- 2511.00511 ID-Composer: Multi-Subject Video Synthesis with Hierarchical Identity
        65602, -- 2510.27135 E-MMDiT: Revisiting Multimodal Diffusion Transformer Design for Fast I
        65658, -- 2510.25970 SplitFlow: Flow Decomposition for Inversion-Free Text-to-Image Editing
        65766, -- 2510.23956 Neural USD: An object-centric framework for iterative editing and cont
        65791, -- 2510.23515 FreeFuse: Multi-Subject LoRA Fusion via Auto Masking at Test Time
        65823, -- 2510.22994 SceneDecorator: Towards Scene-Oriented Story Generation with Scene Pla
        65952, -- 2510.20887 Preventing Shortcuts in Adapter Training via Providing the Shortcuts
        66118, -- 2510.18263 From Competition to Synergy: Unlocking Reinforcement Learning for Subj
        66133, -- 2510.18083 Chimera: Compositional Image Generation using Part-based Concepting
        66363, -- 2510.13702 MVCustom: Multi-View Customized Diffusion via Geometric Latent Renderi
        66679, -- 2510.09475 Few-shot multi-token DreamBooth with LoRa for style-consistent charact
        66820, -- 2510.06827 StyleKeeper: Prevent Content Leakage using Negative Visual Query Guida
        66846, -- 2510.06469 SIGMA-GEN: Structure and Identity Guided Multi-subject Assembly for Im
        66891, -- 2510.05715 AgeBooth: Controllable Facial Aging and Rejuvenation via Diffusion Mod
        66956, -- 2510.04450 REAR: Rethinking Visual Autoregressive Models via Generator-Tokenizer
        67170, -- 2510.01347 Image Generation Based on Image Style Extraction
        67279, -- 2509.26641 Query-Kontext: An Unified Multimodal Model for Image Generation and Ed
        67315, -- 2509.26127 EchoGen: Generating Visual Echoes in Any Scene via Feed-Forward Subjec
        67322, -- 2509.26025 PatchVSR: Breaking Video Diffusion Resolution Limits with Patch-wise V
        67357, -- 2509.25749 ART-VITON: Measurement-Guided Latent Diffusion for Artifact-Free Virtu
        67573, -- 2509.23605 VMDiff: Visual Mixing Diffusion for Limitless Cross-Object Synthesis
        67646, -- 2510.03263 Memory Self-Regeneration: Uncovering Hidden Knowledge in Unlearned Mod
        67927, -- 2509.19203 Vision-Free Retrieval: Rethinking Multimodal Search with Textual Scene
        68045, -- 2509.17120 Stencil: Subject-Driven Generation with Context Guidance
        68194, -- 2509.15031 AutoEdit: Automatic Hyperparameter Tuning for Image Editing
        68890, -- 2509.01181 FocusDPO: Dynamic Preference Optimization for Multi-Subject Personaliz
        68901, -- 2509.01028 CompSlider: Compositional Slider for Disentangled Multiple-Attribute I
        68986, -- 2508.21712 FLORA: Efficient Synthetic Data Generation for Object Detection in Low
        69119, -- 2508.19575 Interact-Custom: Customized Human Object Interaction Image Generation
        69430, -- 2508.14465 DreamSwapV: Mask-guided Subject Swapping for Any Customized Video Edit
        69431, -- 2508.14440 MUSE: Multi-Subject Unified Synthesis via Explicit Layout Semantic Exp
        69538, -- 2508.12718 Single-Reference Text-to-Image Manipulation with Dual Contrastive Deno
        69615, -- 2508.11476 SPG: Style-Prompting Guidance for Style-Specific Content Creation
        69619, -- 2508.11433 MM-R1: Unleashing the Power of Unified Multimodal Large Language Model
        69793, -- 2508.09045 Per-Query Visual Concept Learning
        69803, -- 2508.08949 Lay2Story: Extending Diffusion Transformers for Layout-Togglable Story
        69809, -- 2508.08812 TARA: Token-Aware LoRA for Composable Personalization in Diffusion Mod
        69834, -- 2508.08498 CObL: Toward Zero-Shot Ordinal Layering without User Prompting
        69847, -- 2508.08220 Learning User Preferences for Image Generation Model
        69889, -- 2508.07607 X2Edit: Revisiting Arbitrary-Instruction Image Editing through Self-Co
        70003, -- 2508.06044 NEP: Autoregressive Image Editing via Next Editing Token Prediction
        70199, -- 2508.03402 SCFlow: Implicitly Learning Style and Content Disentanglement with Flo
        70208, -- 2508.03300 Zero Shot Domain Adaptive Semantic Segmentation by Synthetic Data Gene
        70400, -- 2508.00728 YOLO-Count: Differentiable Object Counting for Text-to-Image Generatio
        70438, -- 2508.00319 Steering Guidance for Personalized Text-to-Image Diffusion Models
        70486, -- 2508.03735 StorySync: Training-Free Subject Consistency in Text-to-Image Generati
        70533, -- 2507.22617 Hate in Plain Sight: On the Risks of Moderating AI-Generated Hateful I
        70680, -- 2507.20094 Local Prompt Adaptation for Style-Consistent Multi-Object Generation i
        70802, -- 2507.17963 Zero-Shot Dynamic Concept Personalization with Grid-Based LoRA
        70820, -- 2507.17651 CNS-Bench: Benchmarking Image Classifier Robustness Under Continuous N
        70825, -- 2507.17554 An h-space Based Adversarial Attack for Protection Against Few-shot Pe
        70942, -- 2507.15249 FreeCus: Free Lunch Subject-driven Customization in Diffusion Transfor
        70956, -- 2507.15037 OmniVTON: Training-Free Universal Virtual Try-On
        71188, -- 2507.09619 Generate Aligned Anomaly: Region-Guided Few-Shot Anomaly Image-Mask Pa
        71193, -- 2507.09574 MENTOR: Efficient Multimodal-Conditioned Tuning for Autoregressive Vis
        71280, -- 2507.07591 Stable-Hair v2: Real-World Hair Transfer via Multiple-View Diffusion M
        71393, -- 2507.04599 QR-LoRA: Efficient and Disentangled Fine-tuning via QR Decomposition f
        71422, -- 2507.04038 T-SYNTH: A Knowledge-Based Dataset of Synthetic Breast Images
        71503, -- 2507.01926 IC-Custom: Diverse Image Customization via In-Context Learning
        71511, -- 2507.01792 FreeLoRA: Enabling Training-Free LoRA Fusion for Autoregressive Multi-
        71784, -- 2506.18493 ShowFlow: From Robust Single Concept to Condition-Free Multi-Concept G
        71786, -- 2506.18438 CPAM: Context-Preserving Adaptive Manipulation for Zero-Shot Real Imag
        71919, -- 2506.15742 FLUX.1 Kontext: Flow Matching for In-Context Image Generation and Edit
        71943, -- 2506.13846 Fake it till You Make it: Reward Modeling as Discriminative Prediction
        72073, -- 2506.09612 Consistent Story Generation: Unlocking the Potential of Zigzag Samplin
        72119, -- 2506.07883 Diffusion Counterfactual Generation with Semantic Abduction
        72320, -- 2506.03067 EDITOR: Effective and Interpretable Prompt Inversion for Text-to-Image
        72323, -- 2506.03004 PartComposer: Learning and Composing Part-Level Concepts from Single-I
        72341, -- 2506.02560 DCI: Dual-Conditional Inversion for Boosting Diffusion-Based Image Edi
        72609, -- 2505.21911 AlignGen: Boosting Personalized Image Generation with Cross-Modality P
        72662, -- 2505.20975 DreamBoothDPO: Improving Personalized Generation using Direct Preferen
        72686, -- 2505.20626 ConsiStyle: Style Diversity in Training-Free Consistent T2I Generation
        72789, -- 2505.17994 Segment Anyword: Mask Prompt Inversion for Open-Set Grounded Segmentat
        72798, -- 2505.17796 DetailFusion: A Dual-branch Framework with Detail Enhancement for Comp
        72919, -- 2505.14671 UniCTokens: Boosting Personalized Understanding and Generation via Uni
        73087, -- 2505.08281 Ultra Lowrate Image Compression with Semantic Residual Coding and Comp
        73112, -- 2505.08804 TokenProber: Jailbreaking Text-to-image Models via Fine-grained Word I
        73150, -- 2505.04600 Perpetuating Misogyny with Generative AI: How Model Personalization No
        73237, -- 2504.21836 3D Stylization via Large Reconstruction Model
        73244, -- 2504.21307 The Dual Power of Interpretable Token Embeddings: Jailbreaking Attacks
        73264, -- 2504.20518 Dynamic Attention Analysis for Backdoor Detection in Text-to-Image Dif
        73444, -- 2504.15309 LLM-Enabled Style and Content Regularization for Personalized Text-to-
        73459, -- 2504.13392 POET: Supporting Prompting Creativity and Personalization with Automat
        73555, -- 2504.09097 BIGS: Bimanual Category-agnostic Interaction Reconstruction from Monoc
        73882, -- 2503.19312 ImageGen-CoT: Enhancing Text-to-Image In-context Learning with Chain-o
        73922, -- 2503.17724 Trigger without Trace: Towards Stealthy Backdoor Attack on Text-to-Ima
        74004, -- 2503.13985 DefectFill: Realistic Defect Generation with Inpainting Diffusion Mode
        74075, -- 2503.12018 Compose Your Aesthetics: Empowering Text-to-Image Models with the Prin
        74107, -- 2503.10358 ConceptGuard: Continual Personalized Text-to-Image Generation with For
        74175, -- 2503.08012 Exploring Bias in over 100 Text-to-Image Generative Models
        74623, -- 2502.12489 A Comprehensive Survey on Generative AI for Video-to-Music Generation
        75491, -- 2412.09844 Real-time Identity Defenses against Malicious Personalization of Diffu
        75605, -- 2412.03255 DynamicControl: Adaptive Condition Selection for Improved Text-to-Imag
        75729, -- 2411.16713 Conditional Text-to-Image Generation with Reference Guidance
        75748, -- 2411.13901 Dressing the Imagination: A Dataset for AI-Powered Translation of Text
        75767, -- 2411.12389 Combinational Backdoor Attack against Customized Text-to-Image Models
        75928, -- 2411.02592 Decoupled Data Augmentation for Improving Image Classification
        76224, -- 2410.12822 AVID: Adapting Video Diffusion Models to World Models
        76462, -- 2409.02543 StyleTokenizer: Defining Image Style by a Single Instance for Controll
        76571, -- 2408.09397 Combo: Co-speech holistic 3D human motion generation and efficient cus
        76665, -- 2407.20516 Machine Unlearning in Generative AI: A Survey
        76948, -- 2406.12805 AITTI: Learning Adaptive Inclusive Token for Text-to-Image Generation
        77451, -- 2404.07949 Taming Stable Diffusion for Text to 360° Panorama Image Generation
        77525, -- 2404.01077 Efficient Prompting Methods for Large Language Models: A Survey
        78063, -- 2312.11949 CreativeConnect: Supporting Reference Recombination for Graphic Design
        78160, -- 2312.01800 Collaborative Neural Painting
        78174, -- 2311.18832 Exploiting Diffusion Prior for Generalizable Dense Prediction
        78324, -- 2310.16613 On the Proactive Generation of Unsafe Images From Text-To-Image Models
        78633, -- 2308.09889 DUAW: Data-free Universal Adversarial Watermark against Stable Diffusi
        78660, -- 2308.03921 Spellburst: A Node-based Interface for Exploratory Creative Coding wit
        78803, -- 2307.01898 Generative Artificial Intelligence Consensus in a Trustless Network
        79014, -- 2305.12716 The CLIP Model is Secretly an Image-to-Prompt Converter
        79098, -- 2304.13023 Seeing is not always believing: Benchmarking Human and Model Perceptio
        79368, -- 2302.04222 Glaze: Protecting Artists from Style Mimicry by Text-to-Image Models
        82847, -- 2605.05204 D-OPSD: On-Policy Self-Distillation for Continuously Tuning Step-Disti
        83317, -- 2605.10302 Follow the Mean: Reference-Guided Flow Matching
        83767, -- 2605.08129 Towards Customized Multimodal Role-Play
        83769, -- 2605.25191 Injecting Image Guidance into Text-Conditioned Diffusion Models at Inf
        83818, -- 2605.26111 Squeezing Capacity from Multimodal Large Language Models for Subject-d
        83917, -- 2605.25378 CollectionLoRA: Collecting 50 Effects in 1 LoRA via Multi-Teacher On-P
        83996, -- 2503.22172 Concept-Aware LoRA for Domain-Aligned Segmentation Dataset Generation
        84052, -- 2506.23690 SynMotion: Semantic-Visual Adaptation for Motion Customized Video Gene
        84081, -- 2508.07341 DCoAR: Deep Concept Injection into Unified Autoregressive Models for P
        84340, -- 2512.04485 Not All Birds Look The Same: Identity-Preserving Generation For Birds
        84381, -- 2512.10943 AlcheMinT: Fine-grained Temporal Control for Multi-Reference Consisten
        84402, -- 2512.14236 Elastic3D: Controllable Stereo Video Conversion with Guided Latent Dec
        84485, -- 2601.14602 3D Space as a Scratchpad for Editable Text-to-Image Generation
        84494, -- 2601.20511 Say Cheese! Detail-Preserving Portrait Collection Generation via Natur
        84534, -- 2602.19019 TokenTrace: Multi-Concept Attribution through Watermarked Token Recove
        84611, -- 2602.21977 When LoRA Betrays: Backdooring Text-to-Image Models by Masquerading as
        84682, -- 2603.01010 GeodesicNVS: Probability Density Geodesic Flow Matching for Novel View
        84814, -- 2603.08271 Prototype-Guided Concept Erasure in Diffusion Models
        84831, -- 2603.09771 Ego: Embedding-Guided Personalization of Vision-Language Models
        84865, -- 2603.11795 Intrinsic Concept Extraction Based on Compositional Interpretability
        84932, -- 2603.16100 Reevaluating the Intra-Modal Misalignment Hypothesis in CLIP
        84964, -- 2603.18093 One-to-More: High-Fidelity Training-Free Anomaly Generation with Atten
        85003, -- 2603.20470 DiffGraph: An Automated Agent-driven Model Merging Framework for In-th
        85011, -- 2603.20755 Memory-Efficient Fine-Tuning Diffusion Transformers via Dynamic Patch
        85023, -- 2603.21208 JANUS: A Lightweight Framework for Jailbreaking Text-to-Image Models v
        85093, -- 2603.24570 Anti-I2V: Safeguarding your Photos from Malicious Image-to-video Gener
        85100, -- 2603.24965 Self-Corrected Image Generation with Explainable Latent Rewards
        85223, -- 2604.00849 Disentangling to Re-couple: Resolving the Similarity-Controllability P
        85283, -- 2604.05039 ID-Sim: An Identity-Focused Similarity Metric
        85285, -- 2604.05183 OrthoFuse: Training-free Riemannian Fusion of Orthogonal Style-Concept
        85305, -- 2604.07795 Image-Guided Geometric Stylization of 3D Meshes
        85340, -- 2604.10032 Closed-Form Concept Erasure via Double Projections
        85408, -- 2604.17195 DreamShot: Personalized Storyboard Synthesis with Video Diffusion Prio
        85592, -- 2605.21261 STiTch: Semantic Transition and Transportation in Collaboration for Tr
        85724, -- 2508.11330 Noise Matters: Optimizing Matching Noise for Diffusion Classifiers
        85778, -- 2507.16302 Towards Resilient Safety-driven Unlearning for Diffusion Models agains
        86559, -- 2503.19034 Color Conditional Generation with Sliced Wasserstein Guidance
        86649, -- 2508.10631 Increasing the Utility of Synthetic Images through Chamfer Guidance
        86665, -- 2506.12323 Doctor Approved: Generating Medically Accurate Skin Disease Images thr
        86679, -- 2506.09538 AngleRoCL: Angle-Robust Concept Learning for Physically View-Invariant
        86882, -- 2505.17358 Repurposing Marigold for Zero-Shot Metric Depth Estimation via Defocus
        87243, -- 2510.15194 Salient Concept-Aware Generative Data Augmentation
        87343, -- 2505.17013 When Are Concepts Erased From Diffusion Models?
        87542, -- 2503.18623 Training-Free Personalization via Retrieval and Reasoning on Fingerpri
        87549, -- 2507.20721 AIComposer: Any Style and Content Image Composition via Feature Integr
        87560, -- 2501.09833 Erasing More Than Intended? How Concept Erasure Degrades the Generatio
        87592, -- 2503.11945 Your Text Encoder Can Be An Object-Level Watermarking Controller
        87721, -- 2507.04051 Generate, Refine, and Encode: Leveraging Synthesized Novel Samples for
        87731, -- 2507.20740 Implicit Counterfactual Learning for Audio-Visual Segmentation
        87737, -- 2412.14432 IntroStyle: Training-Free Introspective Style Attribution using Diffus
        87750, -- 2509.13922 Towards Robust Defense against Customization via Protective Perturbati
        87885, -- 2504.13206 DuoLoRA : Cycle-consistent and Rank-disentangled Content-Style Persona
        87894, -- 2411.18068 PersonaCraft: Personalized and Controllable Full-Body Multi-Human Scen
        87904, -- 2506.20983 Rethink Sparse Signals for Pose-guided Text-to-image Generation
        87913, -- 2509.05625 SuMa: A Subspace Mapping Approach for Robust and Effective Concept Era
        88037, -- 2505.02192 DualReal: Adaptive Joint Training for Lossless Identity-Motion Fusion
        88196, -- 2503.23897 Training-Free Text-Guided Image Editing with Visual Autoregressive Mod
        88237, -- 2406.01355 Differentially Private Fine-Tuning of Diffusion Models
        88257, -- 2504.08291 DreamFuse: Adaptive Image Fusion with Diffusion Transformer
        88273, -- 2410.09879 TextMaster: A Unified Framework for Realistic Text Editing via Glyph-S
        88348, -- 2510.04668 ConceptSplit: Decoupled Multi-Concept Personalization of Diffusion Mod
        88455, -- 2510.02296 Continual Personalization for Diffusion Models
        88459, -- 2405.05846 An Inversion-based Measure of Memorization for Diffusion Models
        88498, -- 2510.05660 Teleportraits: Training-Free People Insertion into Any Scene
        89065, -- 2410.02483 Event-Customized Image Generation
        89293, -- 2505.21780 Compositional Scene Understanding through Inverse Generative Modeling
        89440, -- 2505.12427 DragLoRA: Online Optimization of LoRA Adapters for Drag-based Image Ed
        89449, -- 2410.03039 Leveraging Model Guidance to Extract Training Data from Personalized D
        89501, -- 2506.15381 When Model Knowledge meets Diffusion Model: Diffusion-assisted Data-fr
        89756, -- 2506.05867 Stealix: Model Stealing via Prompt Evolution
        90091, -- 2403.13778 Certified Human Trajectory Prediction
        90150, -- 2503.17197 FreeUV: Ground-Truth-Free Realistic Facial UV Texture Recovery via Cro
        90162, -- 2408.13509 Dual-Interrelated Diffusion Model for Few-Shot Anomaly Image Generatio
        90191, -- 2503.16065 Shining Yourself: High-Fidelity Ornaments Virtual Try-on with Diffusio
        90216, -- 2505.01428 Multi-party Collaborative Attention Control for Image Customization
        90264, -- 2503.16630 TriTex: Learning Texture from a Single Mesh via Triplane Semantic Feat
        90277, -- 2504.06675 Probability Density Geodesics in Image Diffusion Latent Space
        90282, -- 2503.15406 Visual Persona: Foundation Model for Full-Body Human Customization
        90336, -- 2502.07802 Movie Weaver: Tuning-Free Multi-Concept Video Personalization with Anc
        90406, -- 2410.24160 Redefining <Creative> in Dictionary: Towards an Enhanced Semantic Unde
        90427, -- 2503.11143 GaussianIP: Identity-Preserving Realistic 3D Human Generation via Huma
        90441, -- 2503.07390 PersonaBooth: Personalized Text-to-Motion Generation
        90504, -- 2412.11638 IDProtector: An Adversarial Noise Encoder to Protect Against ID-Preser
        90565, -- 2504.00430 Data Synthesis with Diverse Styles for Face Recognition via 3DMM-Guide
        90671, -- 2408.16807 STEREO: A Two-Stage Framework for Adversarially Robust Concept Erasing
        90727, -- 2411.15231 IterIS: Iterative Inference-Solving Alignment for LoRA Merging
        90752, -- 2412.20651 Latent Drifting in Diffusion Models for Counterfactual Medical Image S
        90844, -- 2412.00782 Memories of Forgotten Concepts
        90878, -- 2503.19902 ICE: Intrinsic Concept Extraction from a Single Image via Diffusion Mo
        90893, -- 2312.08195 Image is All You Need to Empower Large-scale Diffusion Models for In-D
        90954, -- 2409.03745 ArtiFade: Learning to Generate High-quality Subject from Blemished Ima
        90961, -- 2412.17040 HyperNet Fields: Efficiently Training Hypernetworks without Ground Tru
        91142, -- 2406.19859 MetaDesigner: Advancing Artistic Typography through AI-Driven, User-Ce
        91157, -- 2503.10081 AdvPaint: Protecting Images from Inpainting Manipulation via Adversari
        91700, -- 2501.18950 Fantastic Targets for Concept Erasure in Diffusion Models and Where To
        91811, -- 2410.05116 HERO: Human-Feedback Efficient Reinforcement Learning for Online Diffu
        91945, -- 2503.11005 Cyclic Contrastive Knowledge Transfer for Open-Vocabulary Object Detec
        91974, -- 2406.15020 A3D: Does Diffusion Dream about 3D Alignment?
        92010, -- 2410.00700 Mining your own secrets: Diffusion Classifier Scores for Continual Per
        92054, -- 2412.01197 InstantSwap: Fast Customized Concept Swapping across Sharp Shape Diffe
        92268, -- 2503.13500 Long-horizon Visual Instruction Generation with Logic and Attribute Se
        92369, -- 2406.05641 PaRa: Personalizing Text-to-Image Diffusion via Parameter Rank Reducti
        93411, -- 2503.01122 ACCORD: Alleviating Concept Coupling through Dependence Regularization
        93497, -- 2510.16196 Seeing Through the Brain: New Insights from Decoding Visual Stimuli wi
        93780, -- 2412.08221 Generate Any Scene: Scene Graph Driven Data Synthesis for Visual Gener
        93925, -- 2509.25740 Dragging with Geometry: From Pixels to Geometry-Guided Image Editing
        93959, -- 2505.19519 Preserve and Personalize: Personalized Text-to-Image Diffusion Models
        94157, -- 2507.06547 Concept-TRAK: Understanding how diffusion models learn concepts throug
        94351, -- 2510.14553 Consistent Text-to-Image Generation via Scene De-Contextualization
        94391, -- 2407.20034 MaskInversion: Localized Embeddings via Optimization of Explainability
        94502, -- 2602.11638 Variation-aware Flexible 3D Gaussian Editing
        94756, -- 2506.22685 Mitigating Semantic Collapse in Generative Personalization with Test-T
        94986, -- 2505.18612 Mod-Adapter: Tuning-Free and Versatile Multi-concept Personalization v
        95035, -- 2504.13109 UniEdit-Flow: Unleashing Inversion and Editing in the Era of Flow Mode
        98540, -- 2606.20506 FreeStyle: Free Control of Style-Content Dual-Reference Generation fro
        98586, -- 2606.20556 Thinking in Boxes: 3D Editing in Real Images Made Easy
        98846, -- 2606.27377 DanceOPD: On-Policy Generative Field Distillation
        99264, -- 2602.03410 UnHype: CLIP-Guided Hypernetworks for Dynamic LoRA Unlearning
        99533, -- 2605.15803 Embedding-perturbed Exploration Preference Optimization for Flow Model
        99763, -- 2512.20014 Bring My Cup! Personalizing Vision-Language-Action Models with Visual
        99972, -- 2509.24798 Causal-Adapter: Taming Text-to-Image Diffusion for Faithful Counterfac
        100533, -- 2512.08724 Exposing Hidden Biases in Text-to-Image Models via Automated Prompt Se
        100863, -- 2606.10902 Pose-ICL: 3D-Aware In-Context Learning for Pose-Controllable Subject C
        101368, -- 2601.08379 MMD Guidance: Training-Free Distribution Adaptation for Diffusion Mode
        101895, -- 2605.04970 Skill Neologisms: Towards Skill-based Continual Learning
        103447, -- 2604.07422 Multimodal Large Language Models for Multi-Subject In-Context Image Ge
        103906, -- 2606.27371 Don't Settle at the Mode! Mitigating Diversity Collapse in Pretrained
        103947, -- 2607.11885 Latent-Identity Tuning in Text-to-Image Personalization Models
        104000, -- 2607.05382 Search Beyond What Can Be Taught: Evolving the Knowledge Boundary in A
        104771, -- 2601.18585 GimmBO: Interactive Generative Image Model Merging via Bayesian Optimi
        104829, -- 2602.08198 PEGAsus: 3D Personalization of Geometry and Appearance
        105391, -- 2507.00377 MedDiff-FT: Data-Efficient Diffusion Model Fine-tuning with Structural
        105980, -- 2606.03792 Training-Free Multi-Concept LoRA Composition with Prompt-Aware Weighti
        106793, -- 2511.11060 CareCom: Generative Image Composition with Calibrated Reference Featur
        107019, -- 2410.23736 Modality and Task Adaptation for Enhanced Zero-shot Composed Image Ret
        107061, -- 2505.14537 Personalize Your Gaussian: Consistent 3D Scene Personalization from a
        107225, -- 2512.10433 Targeted Data Protection for Diffusion Model by Matching Training Traj
        107227, -- 2512.05802 Bring Your Dreams to Life: Continual Text-to-Video Customization
        107607, -- 2504.10826 SteerMusic: Enhanced Musical Consistency for Zero-shot Text-Guided and
        107850, -- 2503.07253 AnomalyPainter: Vision-Language-Diffusion Synergy for Realistic and Di
        107919, -- 2512.23519 IdentityStory: Taming Your Identity-Preserving Generator for Human-Cen
        108302, -- 2505.01657 RAGAR: Retrieval Augmented Personalized Image Generation Guided by Rec
        108318, -- 2601.01892 Forget Less by Learning from Parents Through Hierarchical Relationship
        109065, -- 2608.06751 Beyond Starry Night: Shortcut-Aware Control-State Planning for Artist-
        109396, -- 2608.16765 TRACE-Bench: Decomposing and Diagnosing Multi-Reference Image Generati
        109410, -- 2606.22416 Gen2Balance: Generative Balancing for Long-Tailed Video Action Recogni
        109897, -- 2406.18581 Dream-in-Style: Text-to-3D Generation Using Stylized Score Distillatio
        109921, -- 2408.14899 MeshUp: Multi-Target Mesh Deformation via Blended Score Distillation
        110317, -- 2605.27374 ICG: Improving Cover Image Generation via MLLM-based Prompting and Per
        110570, -- 2509.11878 \textit{Do It Yourself (DIY)}: Modifying Images for Poems in a Zero-Sh
        111354, -- 2506.16020 VS-Singer: Vision-Guided Stereo Singing Voice Synthesis with Consisten
        111683, -- 2506.06537 Bridging Audio and Vision: Zero-Shot Audiovisual Segmentation by Conne
        112223, -- 2509.18948 One-shot Embroidery Customization via Contrastive LoRA Modulation
        112258, -- 2511.14848 Gaussian See, Gaussian Do: Semantic 3D Motion Transfer from Multiview
        112298, -- 2509.24288 ASIA: Adaptive 3D Segmentation using Few Image Annotations
        112357, -- 2509.18092 ComposeMe: Attribute-Specific Image Prompts for Controllable Human Ima
        112500, -- 2403.14617 Videoshop: Localized Semantic Video Editing with Noise-Extrapolated Di
        112514, -- 2312.05272 GenQ: Quantization in Low Data Regimes with Generative Synthetic Data
        112557, -- 2305.15171 Diffusion-Generated Pseudo-Observations for High-Quality Sparse-View R
        112632, -- 2402.12688 Robust-Wide: Robust Watermarking against Instruction-driven Image Edit
        112720, -- 2403.15033 Toward Tiny and High-quality Facial Makeup with Data Amplify Learning
        112759, -- 2409.01128 Diffusion-Driven Data Replay: A Novel Approach to Combat Forgetting in
        112763, -- 2408.07147 Controlling the World by Sleight of Hand
        112780, -- 2408.05926 BI-MDRG: Bridging Image History in Multimodal Dialogue Response Genera
        112850, -- 2403.11868 View-Consistent 3D Editing with Gaussian Splatting
        112973, -- 2312.04820 Learn to Optimize Denoising Scores: A Unified and Improved Diffusion P
        112981, -- 2509.20091 Unleashing the Potential of the Semantic Latent Space in Diffusion Mod
        113011, -- 2306.14408 Text-Anchored Score Composition: Tackling Condition Misalignment in Te
        113092, -- 2402.14000 Real-time 3D-aware Portrait Editing from a Single Image
        113290, -- 2311.12066 EditShield: Protecting Unauthorized Image Editing by Instruction-guide
        113427, -- 2406.07487 GLAD: Towards Better Reconstruction with Global and Local Adaptive Dif
        113445, -- 2310.01819 TP2O: Creative Text Pair-to-Object Generation using Balance Swap-Sampl
        113481, -- 2404.18929 DGE: Direct Gaussian 3D Editing by Consistent Multi-view Editing
        113516, -- 2403.11929 LayerDiff: Exploring Text-guided Multi-layered Composable Image Synthe
        113520, -- 2408.00372 Few-shot Defect Image Generation based on Consistency Modeling
        113558, -- 2409.00522 EraseDraw : Learning to Insert Objects by Erasing Them from Images
        113568, -- 2312.02503 SAVE: Protagonist Diversification with Structure Agnostic Video Editin
        113592, -- 2404.05980 Tackling Structural Hallucination in Image Translation with Local Diff
        113635, -- 2407.07249 Few-Shot Image Generation by Conditional Relaxing Diffusion Inversion
        113657, -- 2409.18083 Stable Video Portraits
        115589, -- 2403.08436 PFStorer: Personalized Face Restoration and Super-Resolution
        115594, -- 2403.07773 SemCity: Semantic Scene Generation with Triplane Diffusion
        115619, -- 2405.01356 Improving Subject-Driven Image Synthesis with Subject-Agnostic Guidanc
        115642, -- 2403.19600 Enhance Image Classification via Inter-Class Image Mixup with Diffusio
        115657, -- 2403.18920 CPR: Retrieval Augmented Generation for Copyright Protection
        115703, -- 2311.17083 CLiC: Concept Learning in Context
        115744, -- 2403.15330 Selectively Informative Description can Reduce Undesired Embedding Ent
        115766, -- 2402.00627 CapHuman: Capture Your Moments in Parallel Universes
        115835, -- 2403.18554 CosalPure: Learning Concept from Group Images for Robust Co-Saliency D
        115842, -- 2403.02981 Doubly Abductive Counterfactual Inference for Text-based Image Editing
        115979, -- 2404.16306 TI2V-Zero: Zero-Shot Image Conditioning for Text-to-Video Diffusion Mo
        116018, -- 2311.13608 Breathing Life Into Sketches Using Text-to-Video Priors
        116098, -- 2403.20231 U-VAP: User-specified Visual Appearance Personalization via Decoupled
        116110, -- 2403.19964 FairRAG: Fair Human Generation via Fair Retrieval Augmentation
        116143, -- 2312.00084 Can Protective Perturbation Safeguard Personal Data from Being Exploit
        116144, -- 2403.16510 Make-Your-Anchor: A Diffusion-based 2D Avatar Generation Framework
        116155, -- 2404.15081 Perturbing Attention Gives You More Bang for the Buck: Subtle Imaging
        116222, -- 2312.07322 GenHowTo: Learning to Generate Actions and State Transformations from
        116229, -- 2404.09401 Watermark-embedded Adversarial Examples for Copyright Protection again
        116277, -- 2403.10701 IMPRINT: Generative Object Compositing by Learning Identity-Preserving
        116292, -- 2403.07214 Text-to-Image Diffusion Models are Great Sketch-Photo Matchmakers
        116338, -- 2401.02847 Generating Non-Stationary Textures using Self-Rectification
        116472, -- 2312.12416 Prompting Hard or Hardly Prompting: Prompt Inversion for Text-to-Image
        116604, -- 2403.03431 Towards Understanding Cross and Self-Attention in Stable Diffusion for
        116646, -- 2312.00057 VA3: Virtually Assured Amplification Attack on Probabilistic Copyright
        116663, -- 2311.13127 MetaCloak: Preventing Unauthorized Subject-driven Text-to-image Diffus
        116726, -- 2403.12011 HOIDiffusion: Generating Realistic 3D Hand-Object Interaction Data
        116818, -- 2406.04542 M&M VTO: Multi-Garment Virtual Try-On and Editing
        116835, -- 2403.17004 SD-DiT: Unleashing the Power of Self-supervised Discrimination in Diff
        116901, -- 2403.00644 Diff-Plugin: Revitalizing Details for Diffusion-based Low-level Tasks
        116907, -- 2403.20236 Long-Tailed Anomaly Detection with Learnable Class Names
        116926, -- 2403.16005 Knowledge-Enhanced Dual-stream Zero-shot Composed Image Retrieval
        117016, -- 2305.11577 LeftRefill: Filling Right Canvas based on Left Reference through Gener
        117027, -- 2404.14410 Guess The Unseen: Dynamic 3D Scene Reconstruction from Partial 2D Glim
        117165, -- 2404.01243 A Unified and Interpretable Emotion Representation and Expression Gene
        117186, -- 2403.07222 You'll Never Walk Alone: A Sketch and Text Duet for Fine-Grained Image
        117206, -- 2312.07865 SimAC: A Simple Anti-Customization Method for Protecting Face Privacy
        117234, -- 2401.04608 EmoGen: Emotional Image Content Generation with Text-to-Image Diffusio
        117243, -- 2404.04562 Diffusion Time-step Curriculum for One Image to 3D Generation
        117326, -- 2503.18083 Unified Geometry and Color Compression Framework for Point Clouds via
        117454, -- 2608.11546 Through Van Gogh’s Eyes: Global Style Transfer with Diffusion Model
        118363, -- 2603.13547 NumColor: Precise Numeric Color Control in Text-to-Image Generation
        118395, -- 2512.12598 Setting the Stage: Text-Driven Scene-Consistent Image Generation
        118422, -- 2603.08090 DSH-Bench: A Difficulty- and Scenario-Aware Benchmark with Hierarchica
        118440, -- 2607.06440 PIPBench: A Profile-Inclusive Framework for Personalized Image Generat
        118544, -- 2510.05509 Be Tangential to Manifold: Discovering Riemannian Metric for Diffusion
        118550, -- 2607.14945 Introspective Attention Modulation for Safe Text-to-Image Generation
        118676, -- 2606.28845 Personalizing MLLMs via Reinforced Multimodal Reference Game
        118864, -- 2606.30528 μFlow: Leveraging Average Images for Improving Generalisation of Deepf
        118936, -- 2606.29880 IREU: Identity-Related Encoder-Only Unlearning for Customized Portrait
        118986, -- 2604.08301 GroundingAnomaly: Spatially-Grounded Diffusion for Few-Shot Anomaly Sy
        119558, -- 2607.06918 LoCA: Spatially-Aware Low-Rank Convolutional Adaptation of Vision Foun
        119880, -- 2503.08269 Adv-CPG: A Customized Portrait Generation Framework with Facial Advers
        120047, -- 2512.14542 HiFi-Portrait: Zero-shot Identity-preserved Portrait Generation with H
        120197, -- 2507.02687 APT: Adaptive Personalized Training for Diffusion Models with Limited
        120216, -- 2406.17343 Q-DiT: Accurate Post-Training Quantization for Diffusion Transformers
        120238, -- 2404.05268 MC^2: Multi-concept Guidance for Customized Multi-concept Generation
        120488, -- 2412.01792 CTRL-D: Controllable Dynamic 3D Scene Editing with Personalized 2D Dif
        120501, -- 2502.05165 Multitwine: Multi-Object Compositing with Text and Layout Control
        120544, -- 2506.07750 Difference Inversion: Interpolate and Isolate the Difference with Toke
        120628, -- 2404.04584 D^3: Scaling Up Deepfake Detection by Learning from Discrepancy
        120758, -- 2602.00267 PLACID: Identity-Preserving Multi-Object Compositing via Video Diffusi
        121184, -- 2602.21273 StoryTailor:A Zero-Shot Pipeline for Action-Rich Multi-Subject Visual
        121276, -- 2605.17294 HierEdit: Region-Aware Hierarchical Diffusion for Efficient High-Resol
        122935, -- 2609.38680 ReGain: Restoring Subject Fidelity in Personalization on Synthetic Ima
        123408, -- 2604.01973 NearID: Identity Representation Learning via Near-identity Distractors
        124058, -- 2310.10012 Ring-A-Bell! How Reliable are Concept Removal Methods for Diffusion Mo
        124162, -- 2610.11067 Diffusion Meta-Prompting and Steering for Generalizable Foundation Mod
        125233, -- 2605.07907 Consistency Regularised Gradient Flows for Inverse Problems
        127570, -- 2609.33716 Revisiting Diffusion Fine-Tuning for Unsupervised Domain Adaptation
        127703, -- 2609.36755 Drag as Evidence: Motion-Grounded Latent Recomposition for Drag-Based
        129567, -- 2510.10982 Catch-Only-One: Non-Transferable Examples for Model-Specific Authoriza
        130238, -- 2606.11670 ARGUS: Stacked Multi-View Identity Mosaic Injection for Subject-Preser
        130646, -- 2605.16477 Seeking the Unfamiliar but Memorable: Conceptual Creativity as Meta-Le
        130991, -- 2605.12724 Inline Critic Steers Image Editing
        130997, -- 2606.13768 CineOrchestra: Unified Entity-Centric Conditioning for Cinematic Video
        131556  -- 2610.35684 OmniShowcase: Omnidirectional Subject-Consistent Video Generation from
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
        19200, -- 2308.06721 IP-Adapter: Text Compatible Image Prompt Adapter for Text-to-Image Dif
        24335, -- 2312.03154 ViscoNet: Bridging and Harmonizing Visual and Textual Conditioning for
        27076, -- 2402.05919 Collaborative Control for Geometry-Conditioned PBR Image Generation
        28291, -- 2403.01108 Face Swap via Diffusion Model
        28359, -- 2403.02084 ResAdapter: Domain Consistent Resolution Adapter for Diffusion Models
        30350, -- 2404.09512 Magic Clothing: Controllable Garment-Driven Image Synthesis
        32228, -- 2406.01300 pOps: Photo-Inspired Diffusion Operators
        34833, -- 2407.12705 IMAGDressing-v1: Customizable Virtual Dressing
        35594, -- 2408.03209 IPAdapter-Instruct: Resolving Ambiguity in Image-based Conditioning us
        35708, -- 2408.05206 Multi-Garment Customized Model Generation
        36546, -- 2409.02097 LinFusion: 1 GPU, 1 Minute, 16K Image
        36625, -- 2409.03718 Geometry Image Diffusion: Fast and Data-Efficient Text-to-3D with Imag
        38652, -- 2410.12928 DreamCraft3D++: Efficient Hierarchical 3D Generation with Multi-Plane
        39149, -- 2410.18975 Unbounded: A Generative Infinite Game of Character Life Simulation
        40563, -- 2411.17949 ROICtrl: Boosting Instance Control for Visual Generation
        40575, -- 2411.18135 ModeDreamer: Mode Guiding Score Distillation for Text-to-3D Generation
        40822, -- 2412.01271 MuLan: Adapting Multilingual Diffusion Models for Hundreds of Language
        41488, -- 2412.09618 EasyRef: Omni-Generalized Group Image Reference for Diffusion Models v
        42296, -- 2412.20800 VMix: Improving Text-to-Image Diffusion Model with Cross-Attention Mix
        42400, -- 2501.01097 EliGen: Entity-Level Controlled Image Generation with Regional Attenti
        44604, -- 2502.13951 IP-Composer: Semantic Composition of Visual Concepts
        45112, -- 2502.19673 SubZero: Composing Subject, Style, and Action via Zero-Shot Personaliz
        45709, -- 2503.06568 Conceptrol: Concept Control of Zero-shot Personalized Image Generation
        45750, -- 2503.07027 EasyControl: Adding Efficient and Flexible Control for Diffusion Trans
        46042, -- 2503.10365 Piece it Together: Part-Based Concepting with IP-Priors
        46527, -- 2503.16944 HyperLoRA: Parameter-Efficient Adaptive Generation for Portrait Synthe
        49729, -- 2505.19415 MMIG-Bench: Towards Comprehensive and Explainable Evaluation of Multi-
        52804, -- 2509.21278 Does FLUX Already Know How to Perform Physically Plausible Image Compo
        53150, -- 2510.02253 DragFlow: Unleashing DiT Priors with Region Based Supervision for Drag
        53449, -- 2510.07656 MONKEY: Masking ON KEY-Value Activation Adapter for Personalization
        54165, -- 2511.07499 Toward the Frontiers of Reliable Diffusion Sampling via Adversarial Si
        69046, -- 2508.20505 Describe, Don't Dictate: Semantic Image Editing with Natural Language
        69615, -- 2508.11476 SPG: Style-Prompting Guidance for Style-Specific Content Creation
        76850, -- 2407.01074 Multimodal Conditional 3D Face Geometry Generation
        90233, -- 2504.05838 Mind the Trojan Horse: Image Prompt Adapter Enabling Scalable and Dece
        90504, -- 2412.11638 IDProtector: An Adversarial Noise Encoder to Protect Against ID-Preser
        118393, -- 2607.05088 RADIANCE: Relative Adaptive Denoising with IP-Adapter for Novel Concep
        118459, -- 2606.25578 H-Adapter: Pose-Robust Hairstyle Transfer via Attention-Derived, Sourc
        121428, -- 2605.30230 IP-Adapter Is All You Need: Towards Fine-Tuning-Free Diffusion-Based T
        121777  -- external DynFusion: Rethinking Condition Fusion for Adaptive Multi-Conditional
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
        15672, -- 2305.10431 FastComposer: Tuning-Free Multi-Subject Image Generation with Localize
        16561, -- 2305.18729 Real-World Image Variation by Aligning Diffusion Inversion Chain
        16780, -- 2306.00816 Versatile Backdoor Attack with Visible, Semantic, Sample-Specific, and
        16803, -- 2306.00973 Intelligent Grimm -- Open-ended Visual Storytelling via Latent Diffusi
        18134, -- 2307.04725 AnimateDiff: Animate Your Personalized Text-to-Image Diffusion Models
        18382, -- 2307.09481 AnyDoor: Zero-shot Object-level Image Customization
        20088, -- 2309.01770 StyleAdapter: A Unified Stylized Image Generation Model
        21536, -- 2310.04687 Targeted Attack Improves Protection against Unauthorized Diffusion Cus
        21609, -- 2310.05375 IPDreamer: Appearance-Controllable 3D Object Generation with Complex I
        21809, -- 2310.07653 Mini-DALLE3: Interactive Text to Image by Prompting Large Language Mod
        22185, -- 2310.12190 DynamiCrafter: Animating Open-domain Images with Video Diffusion Prior
        22753, -- 2310.19512 VideoCrafter1: Open Diffusion Models for High-Quality Video Generation
        22956, -- 2311.02343 Stable Diffusion Reference Only: Image Prompt and Blueprint Jointly Gu
        23465, -- 2311.10093 The Chosen One: Consistent Characters in Text-to-Image Diffusion Model
        23859, -- 2311.16498 MagicAnimate: Temporally Consistent Human Image Animation using Diffus
        23892, -- 2311.16933 SparseCtrl: Adding Sparse Controls to Text-to-Video Diffusion Models
        23923, -- 2311.17117 Animate Anyone: Consistent and Controllable Image-to-Video Synthesis f
        23949, -- 2311.17461 When StyleGAN Meets Stable Diffusion: a $\mathscr{W}_+$ Adapter for Pe
        23969, -- 2311.17717 Receler: Reliable Concept Erasing of Text-to-Image Diffusion Models vi
        23986, -- 2311.17917 AvatarStudio: High-fidelity and Animatable 3D Avatar Creation from Tex
        24022, -- 2311.18405 CAT-DM: Controllable Accelerated Virtual Try-on with Diffusion Model
        24036, -- 2311.18635 DiffusionAvatars: Deferred Diffusion for High-fidelity 3D Head Avatars
        24139, -- 2312.00777 VideoBooth: Diffusion-based Video Generation with Image Prompts
        24224, -- 2312.02087 VideoSwap: Customized Video Subject Swapping with Interactive Semantic
        24225, -- 2312.02109 ArtAdapter: Text-to-Image Style Transfer using Multi-Level Style Encod
        24230, -- 2312.02133 Style Aligned Image Generation via Shared Attention
        24239, -- 2312.02150 Readout Guidance: Learning Control from Diffusion Features
        24247, -- 2312.02201 ImageDream: Image-Prompt Multi-view Diffusion for 3D Generation
        24255, -- 2312.02238 X-Adapter: Adding Universal Compatibility of Plugins for Upgraded Diff
        24271, -- 2312.02432 Orthogonal Adaptation for Modular Customization of Diffusion Models
        24290, -- 2312.02663 FaceStudio: Put Your Face Everywhere in Seconds
        24305, -- 2312.02919 Fine-grained Controllable Video Generation via Object Appearance and C
        24314, -- 2312.02970 Alchemist: Parametric Control of Material Properties with Diffusion Mo
        24352, -- 2312.03511 Kandinsky 3.0 Technical Report
        24399, -- 2312.03818 Alpha-CLIP: A CLIP Model Focusing on Wherever You Want
        24430, -- 2312.04364 DemoCaricature: Democratising Caricature Generation with a Rough Sketc
        24433, -- 2312.04410 Smooth Diffusion: Crafting Smooth Latent Spaces in Diffusion Models
        24435, -- 2312.04433 DreamVideo: Composing Your Dream Videos with Customized Subject and Mo
        24437, -- 2312.04461 PhotoMaker: Customizing Realistic Human Photos via Stacked ID Embeddin
        24486, -- 2312.04831 Towards Enhanced Image Inpainting: Mitigating Unwanted Object Insertio
        24503, -- 2312.05107 DreaMoving: A Human Video Generation Framework based on Diffusion Mode
        24638, -- 2312.06738 InstructAny2Pix: Flexible Visual Editing via Multimodal Instruction Fo
        24775, -- 2312.08887 SpeedUpNet: A Plug-and-Play Adapter Network for Accelerating Text-to-I
        24800, -- 2312.09168 DiffusionLight: Light Probes for Free by Painting a Chrome Ball
        24813, -- 2312.09251 VL-GPT: A Generative Pre-trained Transformer for Vision and Language U
        24907, -- 2312.10899 MagicScroll: Nontypical Aspect-Ratio Image Generation for Visual Story
        25052, -- 2312.13271 Repaint123: Fast and High-quality One Image to 3D Generation with Prog
        25086, -- 2312.13913 Paint3D: Paint Anything 3D with Lighting-Less Texture Diffusion Models
        25089, -- 2312.13964 PIA: Your Personalized Image Animator via Plug-and-Play Modules in Tex
        25232, -- 2312.16272 SSR-Encoder: Encoding Selective Subject Representation for Subject-Dri
        25405, -- 2401.01256 VideoStudio: Generating Consistent-Content and Multi-Scene Videos
        25417, -- 2401.01456 ColorizeDiffusion: Adjustable Sketch Colorization with Reference Image
        25443, -- 2401.01827 Moonshot: Towards Controllable Video Generation and Editing with Multi
        25718, -- 2401.06105 PALP: Prompt Aligned Personalization of Text-to-Image Models
        25818, -- 2401.07519 InstantID: Zero-shot Identity-Preserving Generation in Seconds
        25945, -- 2401.09414 Vlogger: Make Your Dream A Vlog
        26059, -- 2401.10889 Synthesizing Moving People with 3D Control
        26179, -- 2401.12596 UniHDA: A Unified and Versatile Framework for Multi-Modal Hybrid Domai
        26266, -- 2401.13974 BootPIG: Bootstrapping Zero-shot Personalized Image Generation Capabil
        26276, -- 2401.14066 CreativeSynth: Cross-Art-Attention for Artistic Image Synthesis with M
        26405, -- 2401.15975 StableIdentity: Inserting Anybody into Anywhere at First Sight
        26552, -- 2402.00126 Common Sense Reasoning for Deepfake Detection
        26576, -- 2402.00631 Beyond Inserting: Learning Identity Embedding for Semantic-Fidelity Pe
        27021, -- 2402.05195 $λ$-ECLIPSE: Multi-Concept Personalized Text-to-Image Diffusion Models
        27325, -- 2402.09368 Magic-Me: Identity-Specific Video Customized Diffusion
        27384, -- 2402.10207 Rewards-in-Context: Multi-objective Alignment of Foundation Models wit
        27658, -- 2402.12908 RealCompo: Balancing Realism and Compositionality Improves Text-to-Ima
        27663, -- 2402.12974 Visual Style Prompting with Swapping Self-Attention
        27751, -- 2402.13929 SDXL-Lightning: Progressive Adversarial Diffusion Distillation
        28025, -- 2402.17113 Transparent Image Layer Diffusion using Latent Transparency
        28037, -- 2402.17214 CharacterGen: Efficient 3D Character Generation from Single Images wit
        28055, -- 2402.17412 DiffuseKronA: A Parameter Efficient Fine-tuning Method for Personalize
        28067, -- 2402.17525 Diffusion Model-Based Image Editing: A Survey
        28118, -- 2402.18078 Coarse-to-Fine Latent Diffusion for Pose-Guided Person Image Synthesis
        28342, -- 2403.01779 OOTDiffusion: Outfitting Fusion based Latent Diffusion for Controllabl
        28344, -- 2403.01800 AtomoVideo: High Fidelity Image-to-Video Generation
        28417, -- 2403.02827 Tuning-Free Noise Rectification for High Fidelity Image-to-Video Gener
        28564, -- 2403.05056 Stealing Stable Diffusion Prior for Robust Monocular Depth Estimation
        28569, -- 2403.05135 ELLA: Equip Diffusion Models with LLM for Enhanced Semantic Alignment
        28570, -- 2403.05139 Improving Diffusion Models for Authentic Virtual Try-on in the Wild
        28682, -- 2403.06951 DEADiff: An Efficient Stylization Diffusion Model with Disentangled Re
        28738, -- 2403.07764 Stable-Makeup: When Real-World Makeup Transfer Meets Diffusion Model
        28825, -- 2403.09055 SemanticDraw: Towards Real-Time Interactive Content Creation from Imag
        28832, -- 2403.09140 Sculpt3D: Multi-View Consistent Text-to-3D Generation with Sparse 3D P
        28873, -- 2403.09625 Make-Your-3D: Fast and Consistent Subject-Driven 3D Content Generation
        28953, -- 2403.10783 StableGarment: Garment-Centric Generation via Stable Diffusion
        28974, -- 2403.11053 OSTAF: A One-Shot Tuning Method for Improved Attribute-Focused T2I Per
        28978, -- 2403.11105 Source Prompt Disentangled Inversion for Boosting Image Editability wi
        28988, -- 2403.11207 MindEye2: Shared-Subject Models Enable fMRI-To-Image With 1 Hour of Da
        29024, -- 2403.11641 Arc2Face: A Foundation Model for ID-Consistent Human Faces
        29035, -- 2403.11781 Infinite-ID: Identity-preserved Personalization via ID-semantics Decou
        29069, -- 2403.12032 Generic 3D Diffusion Adapter Using Controlled Multi-View Editing
        29113, -- 2403.12706 AnimateDiff-Lightning: Cross-Model Diffusion Distillation
        29141, -- 2403.12962 FRESCO: Spatial-Temporal Correspondence for Zero-Shot Video Translatio
        29191, -- 2403.13535 IDAdapter: Learning Mixed Features for Tuning-Free Personalization of
        29271, -- 2403.14572 Implicit Style-Content Separation using B-LoRA
        29274, -- 2403.14599 MyVLM: Personalizing VLMs for User-Specific Queries
        29276, -- 2403.14608 Parameter-Efficient Fine-Tuning for Large Models: A Comprehensive Surv
        29299, -- 2403.14781 Champ: Controllable and Consistent Human Image Animation with 3D Param
        29300, -- 2403.14790 Latent Diffusion Models for Attribute-Preserving Image Anonymization
        29302, -- 2403.14828 Multimodal-Conditioned Latent Diffusion Models for Fashion Image Editi
        29315, -- 2403.15059 MM-Diff: High-Fidelity Image Personalization via Multi-Modal Condition
        29444, -- 2403.17001 VP3D: Unleashing 2D Visual Prompt for Text-to-3D Generation
        29448, -- 2403.17008 FlashFace: Human Image Personalization with High-fidelity Identity Pre
        29454, -- 2403.17217 DiffusionAct: Controllable Diffusion Autoencoder for One-shot Face Ree
        29535, -- 2403.18342 Learning Inclusion Matching for Animation Paint Bucket Colorization
        29546, -- 2403.18461 DiffStyler: Diffusion-based Localized Image Style Transfer
        29554, -- 2403.18660 InstructBrush: Learning Attention-based Instruction Optimization for I
        29627, -- 2403.19645 GANTASTIC: GAN-based Transfer of Interpretable Directions for Disentan
        29666, -- 2403.20193 Motion Inversion for Video Customization
        29824, -- 2404.01709 Upsample Guidance: Scale Up Diffusion Models without Training
        29853, -- 2404.02101 CameraCtrl: Enabling Camera Control for Text-to-Video Generation
        29887, -- 2404.02733 InstantStyle: Free Lunch towards Style-Preserving in Text-to-Image Gen
        29955, -- 2404.03620 LCM-Lookahead for Encoder-based Text-to-Image Personalization
        30036, -- 2404.04828 Strictly-ID-Preserved and Controllable Accessory Advertising Image Gen
        30037, -- 2404.04833 ShoeModel: Learning to Wear on the User-specified Shoes via Diffusion
        30081, -- 2404.05595 UniFL: Improve Latent Diffusion Model via Unified Feedback Learning
        30092, -- 2404.05674 MoMA: Multimodal LLM Adapter for Fast Personalized Image Generation
        30145, -- 2404.06425 ZeST: Zero-Shot Material Transfer from a Single Image
        30146, -- 2404.06429 Magic-Boost: Boost 3D Generation with Multi-View Conditioned Diffusion
        30149, -- 2404.06451 SmartControl: Enhancing ControlNet for Handling Rough Visual Condition
        30216, -- 2404.07554 CAT: Contrastive Adapter Training for Personalized Image Generation
        30253, -- 2404.07987 ControlNet++: Improving Conditional Controls with Efficient Consistenc
        30389, -- 2404.09990 HQ-Edit: A High-Quality Dataset for Instruction-based Image Editing
        30406, -- 2404.10267 OneActor: Consistent Character Generation via Cluster-Conditioned Guid
        30530, -- 2404.12333 Customizing Text-to-Image Diffusion with Object Viewpoint Control
        30622, -- 2404.13680 Zero-shot High-fidelity and Pose-controllable Character Animation
        30646, -- 2404.14239 MultiBooth: Towards Generating All Your Concepts in an Image from Text
        30711, -- 2404.15267 From Parts to Whole: A Unified Reference Framework for Controllable Hu
        30713, -- 2404.15275 ID-Animator: Zero-Shot Identity-Preserving Human Video Generation
        30717, -- 2404.15449 ID-Aligner: Enhancing Identity-Preserving Text-to-Image Generation wit
        30729, -- 2404.15677 CharacterFactory: Sampling Consistent Characters with GANs for Diffusi
        30746, -- 2404.16022 PuLID: Pure and Lightning ID Customization via Contrastive Alignment
        30785, -- 2404.16771 ConsistentID: Portrait Generation with Multimodal Fine-Grained Identit
        30925, -- 2404.19427 InstantFamily: Masked Attention for Zero-shot Multi-ID Image Generatio
        31012, -- 2405.01434 StoryDiffusion: Consistent Self-Attention for Long-Range Image and Vid
        31023, -- 2405.01536 Customizing Text-to-Image Models with a Single Image Pair
        31169, -- 2405.05806 MasterWeaver: Taming Editability and Face Identity for Personalized Te
        31214, -- 2405.06948 Training-free Subject-Enhanced Attention Guidance for Compositional Te
        31231, -- 2405.07510 PeRFlow: Piecewise Rectified Flow as Universal Plug-and-Play Accelerat
        31256, -- 2405.07913 CTRLorALTer: Conditional LoRAdapter for Efficient 0-Shot Control & Alt
        31481, -- 2405.12970 Face Adapter for Pre-Trained Diffusion Models with Fine-Grained ID and
        31530, -- 2405.13722 LightningDrag: Lightning Fast and Accurate Drag-based Image Editing Em
        31566, -- 2405.14201 FreeTuner: Any Subject in Any Style with Training-free Diffusion
        31606, -- 2405.14677 RectifID: Personalizing Rectified Flow with Anchored Classifier Guidan
        31619, -- 2405.14785 EditWorld: Simulating World Dynamics for Instruction-Following Image E
        31631, -- 2405.14857 Conditional Diffusion on Web-Scale Image Pairs leads to Diverse Image
        31774, -- 2405.16537 I2VEdit: First-Frame-Guided Video Editing via Image-to-Video Diffusion
        31777, -- 2405.16570 ID-to-3D: Expressive ID-guided 3D Heads via Score Distillation Samplin
        31845, -- 2405.17401 RB-Modulation: Training-Free Personalization of Diffusion Models using
        31921, -- 2405.18172 AnyFit: Controllable Virtual Try-on for Any Combination of Attire Acro
        32098, -- 2405.20343 Unique3D: High-Quality and Efficient 3D Mesh Generation from a Single
        32117, -- 2405.20674 4Diffusion: Multi-view Video Diffusion Model for 4D Generation
        32234, -- 2406.01388 AutoStudio: Crafting Consistent Subjects in Multi-turn Interactive Ima
        32272, -- 2406.01954 Plug-and-Play Diffusion Distillation
        32285, -- 2406.02184 GraVITON: Graph based garment warping with attention guided inversion
        32307, -- 2406.02511 V-Express: Conditional Dropout for Progressive Training of Portrait Vi
        32442, -- 2406.04277 VideoTetris: Towards Compositional Text-to-Video Generation
        32514, -- 2406.05000 AttnDreamBooth: Towards Text-Aligned Personalized Text-to-Image Genera
        32631, -- 2406.06424 Margin-aware Preference Optimization for Aligning Diffusion Models wit
        32691, -- 2406.07209 MS-Diffusion: Multi-subject Zero-shot Image Personalization with Layou
        32734, -- 2406.07540 Ctrl-X: Controlling Structure and Appearance for Text-To-Image Generat
        32738, -- 2406.07547 Zero-shot Image Editing with Reference Imitation
        32827, -- 2406.08659 Vivid-ZOO: Multi-View Video Generation with Diffusion Model
        32864, -- 2406.09162 EMMA: Your Text-to-Image Diffusion Model Can Secretly Accept Multi-Mod
        32888, -- 2406.09368 CLIPAway: Harmonizing Focused Embeddings for Removing Objects via Diff
        32903, -- 2406.09413 Interpreting the Weight Space of Customized Diffusion Models
        33129, -- 2406.11643 CustAny: Customizing Anything from A Single Example
        33377, -- 2406.14130 ExVideo: Extending Video Diffusion Models via Parameter-Efficient Post
        33580, -- 2406.16537 Character-Adapter: Prompt-Guided Region Control for High-Fidelity Char
        33611, -- 2406.16855 DreamBench++: A Human-Aligned Benchmark for Personalized Image Generat
        33765, -- 2406.18790 MUMU: Bootstrapping Multimodal Image Generation from Text-to-Image Dat
        33778, -- 2406.18958 AnyControl: Create Your Artwork with Versatile Control on Text-to-Imag
        33917, -- 2407.00788 InstantStyle-Plus: Style Transfer with Content-Preserving in Text-to-I
        33965, -- 2407.01414 StyleShot: A Snapshot on Any Style
        33975, -- 2407.01494 FoleyCrafter: Bring Silent Videos to Life with Lifelike and Synchroniz
        33994, -- 2407.01790 Label-free Neural Semantic Image Synthesis
        34058, -- 2407.02489 Magic Insert: Style-Aware Drag-and-Drop
        34274, -- 2407.05552 Ada-adapter:Fast Few-shot Style Personlization of Diffusion Model with
        34446, -- 2407.07875 Generative Image as Action Models
        34451, -- 2407.08019 Coherent and Multi-modality Image Inpainting via Latent Space Optimiza
        34505, -- 2407.08674 Still-Moving: Customized Video Generation without Customized Video Dat
        34536, -- 2407.09012 TCAN: Animating Human Images with Temporally Consistent Pose Guidance
        34727, -- 2407.11398 Animate3D: Animating Any 3D Model with Multi-view Video Diffusion
        34788, -- 2407.12164 Subject-driven Text-to-Image Generation via Preference-based Reinforce
        34841, -- 2407.12781 VD3D: Taming Large Video Diffusion Transformers for 3D Camera Control
        35042, -- 2407.15446 Text2Place: Affordance-aware Text Guided Human Placement
        35078, -- 2407.15886 CatVTON: Concatenation Is All You Need for Virtual Try-On with Diffusi
        35114, -- 2407.16564 Audio Prompt Adapter: Unleashing Music Editing Abilities for Text-to-M
        35308, -- 2407.20175 Towards Localized Fine-Grained Control for Facial Expression Generatio
        35567, -- 2408.02657 Lumina-mGPT: Illuminate Flexible Photorealistic Text-to-Image Generati
        35687, -- 2408.04785 BRAT: Bonus oRthogonAl Token for Architecture Agnostic Textual Inversi
        35699, -- 2408.05083 PreciseControl: Enhancing Text-To-Image Diffusion Models with Fine-Gra
        35741, -- 2408.05939 UniPortrait: A Unified Framework for Identity-Preserving Single- and M
        35818, -- 2408.07116 Generative Photomontage
        35831, -- 2408.07433 MagicFace: Training-free Universal-Style Human Image Customized Synthe
        35959, -- 2408.09744 RealCustom++: Representing Images as Real-Word for Real-Time Customiza
        36035, -- 2408.11001 MegaFusion: Extend Diffusion Models towards Higher-resolution Image Ge
        36111, -- 2408.11915 Video-Foley: Two-Stage Video-To-Sound Generation via Temporal Event Co
        36135, -- 2408.12340 VTON-HandFit: Virtual Try-on for Arbitrary Hand Pose Guided by Hand Pr
        36141, -- 2408.12429 FlexEdit: Marrying Free-Shape Masks to VLLM for Flexible Image Editing
        36266, -- 2408.14819 Build-A-Scene: Interactive 3D Layout Control for Diffusion-Based Image
        36378, -- 2408.16506 Alignment is All You Need: A Training-free Augmentation Strategy for P
        36391, -- 2408.16766 CSGO: Content-Style Composition in Text-to-Image Generation
        36483, -- 2409.01055 Follow-Your-Canvas: Higher-Resolution Video Outpainting with Extensive
        36486, -- 2409.01086 DPDEdit: Detail-Preserved Diffusion Models for Multimodal Fashion Imag
        36506, -- 2409.01392 ComfyBench: Benchmarking LLM-based Agents in ComfyUI for Autonomously
        36593, -- 2409.02979 Vec2Face: Scaling Face Dataset Generation with Loosely Constrained Vec
        36697, -- 2409.05606 CustomContrast: A Multilevel Contrastive Perspective For Subject-Drive
        36804, -- 2409.08026 Scribble-Guided Diffusion for Training-free Text-to-Image Generation
        36814, -- 2409.08240 IFAdapter: Instance Feature Control for Grounded Text-to-Image Generat
        36901, -- 2409.09593 One-Shot Learning for Pose-Guided Person Image Synthesis in the Wild
        36999, -- 2409.11340 OmniGen: Unified Image Generation
        37077, -- 2409.12576 StoryMaker: Towards Holistic Consistent Characters in Text-to-image Ge
        37120, -- 2409.13346 Imagine yourself: Tuning-Free Personalized Image Generation
        37228, -- 2409.15278 PixWizard: Versatile Image-to-Image Visual Assistant with Open-Languag
        37321, -- 2409.16949 DALDA: Data Augmentation Leveraging Diffusion Model and LLM with Adapt
        37325, -- 2409.17049 ControlCity: A Multimodal Diffusion Model Based Approach for Accurate
        37370, -- 2409.17740 AnyLogo: Symbiotic Subject-Driven Diffusion System with Gemini Status
        37382, -- 2409.17920 Resolving Multi-Condition Confusion for Finetuning-Free Personalized I
        37391, -- 2409.18071 FreeEdit: Mask-free Reference-based Image Editing with Multi-modal Ins
        37455, -- 2409.19111 Fusion is all you need: Face Fusion for Customized Identity-Preserving
        37484, -- 2409.19580 High Quality Human Image Animation using Regional Supervision and Moti
        37489, -- 2409.19624 Storynizor: Consistent Story Generation via Inter-Frame Synchronized a
        37521, -- 2409.19946 Illustrious: an Open Advanced Illustration Model
        37563, -- 2410.00086 ACE: All-round Creator and Editor Following Instructions via Diffusion
        37632, -- 2410.01262 Improving Fine-Grained Control via Aggregation of Multiple Diffusion M
        37681, -- 2410.01731 ComfyGen: Prompt-Adaptive Workflows for Text-to-Image Generation
        37713, -- 2410.02055 Using Style Ambiguity Loss to Improve Aesthetics of Diffusion Models
        37716, -- 2410.02067 DisEnvisioner: Disentangled and Enriched Visual Prompt for Customized
        37924, -- 2410.04052 Beyond Imperfections: A Conditional Inpainting Approach for End-to-End
        37983, -- 2410.04844 PostEdit: Posterior Sampling for Efficient Zero-Shot Image Editing
        37985, -- 2410.04932 OmniBooth: Learning Latent Control for Image Synthesis with Multi-moda
        38040, -- 2410.05470 Image Watermarks are Removable Using Controllable Regeneration from Cl
        38110, -- 2410.06244 Story-Adapter: A Training-free Iterative Framework for Long Story Visu
        38131, -- 2410.06551 InstantIR: Blind Image Restoration with Instant Generative Reference
        38177, -- 2410.07113 Personalized Visual Instruction Tuning
        38184, -- 2410.07155 Trans4D: Realistic Geometry-Aware Transition for Compositional Text-to
        38185, -- 2410.07157 InstructG2I: Synthesizing Images from Multimodal Attributed Graphs
        38231, -- 2410.07763 HARIVO: Harnessing Text-to-Image Models for Video Generation
        38267, -- 2410.08168 ZeroComp: Zero-shot Object Compositing from Image Intrinsics via Diffu
        38268, -- 2410.08181 RGM: Reconstructing High-fidelity 3D Car Assets with Relightable 3D-GS
        38387, -- 2410.09802 EBDM: Exemplar-guided Image Translation with Brownian-bridge Diffusion
        38392, -- 2410.09865 SynFER: Towards Boosting Facial Expression Recognition with Synthetic
        38515, -- 2410.11236 Ctrl-U: Robust Conditional Image Generation via Uncertainty-aware Rewa
        38530, -- 2410.11439 A Simple Approach to Unifying Diffusion-based Conditional Generation
        38594, -- 2410.12312 FaceChain-FACT: Face Adapter with Decoupled Training for Identity-pres
        38612, -- 2410.12501 DH-VTON: Deep Text-Driven Virtual Try-On via Hybrid Attention Learning
        38621, -- 2410.12669 3DIS: Depth-Driven Decoupled Instance Synthesis for Text-to-Image Gene
        38701, -- 2410.13360 RAP: Retrieval-Augmented Personalization for Multimodal Large Language
        38744, -- 2410.13807 ConsisSR: Delving Deep into Consistency in Diffusion-based Image Super
        38750, -- 2410.13830 DreamVideo-2: Zero-Shot Subject-Driven Video Customization with Precis
        38797, -- 2410.14324 HiCo: Hierarchical Controllable Diffusion Model for Layout-to-image Ge
        38851, -- 2410.15027 Group Diffusion Transformers are Unsupervised Multitask Learners
        38909, -- 2410.15957 CamI2V: Camera-Controlled Image-to-Video Diffusion Model
        39122, -- 2410.18666 DreamClear: High-Capacity Real-World Image Restoration with Privacy-Sa
        39179, -- 2410.19424 Paint Bucket Colorization Using Anime Character Color Design Sheets
        39293, -- 2410.21299 TV-3DG: Mastering Text-to-3D Customized Generation with Visual Prompt
        39370, -- 2410.22771 FuseAnyPart: Diffusion-Driven Facial Parts Swapping via Multiple Refer
        39379, -- 2410.22901 HelloMeme: Integrating Spatial Knitting Attentions to Embed High-Level
        39388, -- 2410.23054 Controlling Language and Diffusion Models by Transporting Activations
        39407, -- 2410.23280 RelationBooth: Towards Relation-Aware Customized Object Generation
        39433, -- 2410.23775 In-Context LoRA for Diffusion Transformers
        39608, -- 2411.02336 MVPaint: Synchronized Multi-View Diffusion for Painting Anything 3D
        39693, -- 2411.03982 ReEdit: Multimodal Exemplar-Based Image Editing with Diffusion Models
        39716, -- 2411.04357 MegaPortrait: Revisiting Diffusion Control for High-fidelity Portrait
        39755, -- 2411.04989 SG-I2V: Self-Guided Trajectory Control in Image-to-Video Generation
        39762, -- 2411.05003 ReCapture: Generative Video Camera Controls for User-Provided Videos u
        39851, -- 2411.06525 I2VControl-Camera: Precise Video Camera Control with Adjustable Motion
        39853, -- 2411.06558 Region-Aware Text-to-Image Generation via Hard Binding and Soft Refine
        40056, -- 2411.10501 OnlyFlow: Optical Flow based Motion Conditioning for Video Diffusion M
        40179, -- 2411.12872 From Text to Pose to Image: Improving Diffusion Model Control and Qual
        40195, -- 2411.13127 Adapting Vision Foundation Models for Robust Cloud Segmentation in Rem
        40230, -- 2411.13632 ID-Patch: Robust ID Association for Group Photo Personalization
        40293, -- 2411.14793 Style-Friendly SNR Sampler for Style-Driven Generation
        40319, -- 2411.15098 OminiControl: Minimal and Universal Control for Diffusion Transformer
        40338, -- 2411.15245 AnyText2: Visual Text Generation and Editing With Customizable Attribu
        40339, -- 2411.15252 LocRef-Diffusion:Tuning-Free Layout and Appearance-Guided Generation
        40343, -- 2411.15277 Foundation Cures Personalization: Recovering Facial Personalized Model
        40354, -- 2411.15435 What Makes a Scene ? Scene Graph-based Evaluation and Feedback for Con
        40360, -- 2411.15466 Large-Scale Text-to-Image Model with Inpainting is a Zero-Shot Subject
        40384, -- 2411.15738 AnyEdit: Mastering Unified High-Quality Image Editing for Any Idea
        40422, -- 2411.16318 One Diffusion to Generate Them All
        40446, -- 2411.16657 DreamRunner: Fine-Grained Storytelling Video Generation with Retrieval
        40462, -- 2411.16801 Controllable Human Image Generation with Personalized Multi-Garments
        40481, -- 2411.17017 TED-VITON: Transformer-Empowered Diffusion Models for Virtual Try-On
        40484, -- 2411.17048 PersonalVideo: High ID-Fidelity Video Customization without Dynamic an
        40497, -- 2411.17223 DreamMix: Decoupling Object Attributes for Enhanced Editability in Cus
        40504, -- 2411.17323 InsightEdit: Towards Better Instruction Following for Image Editing
        40511, -- 2411.17423 DRiVE: Diffusion-based Rigging Empowers Generation of Versatile and Ex
        40513, -- 2411.17440 Identity-Preserving Text-to-Video Generation by Frequency Decompositio
        40543, -- 2411.17697 StableAnimator: High-Quality Identity-Preserving Human Image Animation
        40551, -- 2411.17786 DreamCache: Finetuning-Free Lightweight Personalized Image Generation
        40588, -- 2411.18281 MotionCharacter: Identity-Preserving and Motion Controllable Human Vid
        40590, -- 2411.18293 HiFiVFS: High Fidelity Video Face Swapping
        40593, -- 2411.18350 TryOffDiff: Virtual-Try-Off via High-Fidelity Garment Reconstruction u
        40613, -- 2411.18616 Diffusion Self-Distillation for Zero-Shot Customized Image Generation
        40622, -- 2411.18665 SpotLight: Shadow-Guided Object Relighting via Diffusion
        40662, -- 2411.19261 Improving Multi-Subject Consistency in Open-Domain Image Generation wi
        40666, -- 2411.19292 UrbanCAD: Towards Highly Controllable and Photorealistic 3D Vehicles f
        40675, -- 2411.19390 DreamBlend: Advancing Personalized Fine-tuning of Text-to-Image Diffus
        40690, -- 2411.19528 RAGDiffusion: Faithful Cloth Generation via External Knowledge Assimil
        40740, -- 2412.00136 FonTS: Text Rendering with Typography and Style Controls
        40793, -- 2412.00857 Advanced Video Inpainting Using Optical Flow-Guided Efficient Diffusio
        40813, -- 2412.01160 ControlFace: Harnessing Facial Parametric Control for Face Rigging
        40820, -- 2412.01254 EmojiDiff: Advanced Facial Expression Control with High Identity Prese
        40834, -- 2412.01485 SerialGen: Personalized Image Generation by First Standardization Then
        40881, -- 2412.02114 OmniCreator: Self-Supervised Unified Generation with Universal Editing
        40940, -- 2412.02912 ShapeWords: Guiding Text-to-Image Synthesis with 3D Shape-Aware Prompt
        40944, -- 2412.03011 Human Multi-View Synthesis from a Single-View Model:Transferred Body a
        40957, -- 2412.03150 Appearance Matching Adapter for Exemplar-based Semantic Image Synthesi
        40962, -- 2412.03177 PatchDPO: Patch-level DPO for Finetuning-free Personalized Image Gener
        40974, -- 2412.03347 DIVE: Taming DINO for Subject-Driven Video Editing
        40989, -- 2412.03552 Imagine360: Immersive 360 Video Generation from Perspective Anchor
        41006, -- 2412.03632 MV-Adapter: Multi-view Consistent Image Generation Made Easy
        41019, -- 2412.03812 Pinco: Position-induced Consistent Adapter for Diffusion Transformer i
        41023, -- 2412.03859 CreatiLayout: Siamese Multimodal Diffusion Transformer for Creative La
        41042, -- 2412.04146 AnyDressing: Customizable Multi-Garment Virtual Dressing via Latent Di
        41051, -- 2412.04301 SwiftEdit: Lightning Fast Text-Guided Image Editing via One-Step Diffu
        41136, -- 2412.05101 The Silent Prompt: Initial Noise as Implicit Guidance for Goal-Driven
        41139, -- 2412.05148 LoRA.rar: Learning to Merge LoRAs via Hypernetworks for Subject-Style
        41308, -- 2412.07589 DiffSensei: Bridging Multi-Modal LLMs and Diffusion Models for Customi
        41313, -- 2412.07674 FiVA: Fine-grained Visual Attribute Dataset for Text-to-Image Diffusio
        41324, -- 2412.07744 StyleMaster: Stylize Your Video with Artistic Generation and Translati
        41326, -- 2412.07750 Multi-Shot Character Consistency for Text-to-Video Generation
        41328, -- 2412.07754 PortraitTalk: Towards Customizable One-Shot Audio-to-Talking Face Gene
        41341, -- 2412.07774 UniReal: Universal Image Generation and Editing via Learning Real-worl
        41386, -- 2412.08503 StyleStudio: Text-Driven Style Transfer with Selective Control of Styl
        41441, -- 2412.09169 DECOR:Decomposition and Projection of Text Embeddings for Text-to-Imag
        41451, -- 2412.09349 DisPose: Disentangling Pose Guidance for Controllable Human Image Anim
        41492, -- 2412.09622 LoRACLR: Contrastive Adaptation for Customization of Diffusion Models
        41498, -- 2412.09694 Omni-ID: Holistic Identity Representation Designed for Generative Task
        41595, -- 2412.11058 SHMT: Self-supervised Hierarchical Makeup Transfer via Latent Diffusio
        41661, -- 2412.11815 ColorFlow: Retrieval-Augmented Image Sequence Colorization
        41709, -- 2412.12242 OmniPrism: Learning Disentangled Visual Concept for Image Generation
        41714, -- 2412.12391 Efficient Scaling of Diffusion Transformers for Text-to-Image Generati
        41789, -- 2412.13195 CoMPaSS: Enhancing Spatial Understanding in Text-to-Image Diffusion Mo
        41849, -- 2412.14158 AKiRa: Augmentation Kit on Rays for optical video generation
        41858, -- 2412.14173 AniDoc: Animation Creation Made Easier
        41993, -- 2412.16112 CLEAR: Conv-Like Linearization Revs Pre-Trained Diffusion Transformers
        42059, -- 2412.17098 DreamOmni: Unified Image Generation and Editing
        42100, -- 2412.17610 Personalized Large Vision-Language Models
        42184, -- 2412.18608 PartGen: Part-level 3D Generation and Reconstruction with Multi-View D
        42201, -- 2412.18928 UNIC-Adapter: Unified Image-instruction Adapter with Multi-modal Trans
        42203, -- 2412.18945 Single Trajectory Distillation for Accelerating Image and Video Style
        42254, -- 2412.19853 Conditional Balance: Improving Multi-Conditioning Trade-Offs in Image
        42292, -- 2412.20725 Dialogue Director: Bridging the Gap in Dialogue Visualization for Mult
        42381, -- 2501.00816 MixSA: Training-free Reference-based Sketch Extraction via Mixture-of-
        42426, -- 2501.01407 Nested Attention: Semantic-aware Attention Values for Concept Personal
        42452, -- 2501.01790 Ingredients: Blending Custom Photos with Video Diffusion Transformers
        42477, -- 2501.02355 CorrFill: Enhancing Faithfulness in Reference-based Inpainting with Co
        42480, -- 2501.02376 Origin Identification for Text-Guided Image-to-Image Diffusion Models
        42564, -- 2501.03630 MC-VTON: Minimal Control Virtual Try-On Diffusion Transformer
        42582, -- 2501.03931 Magic Mirror: ID-Preserved Video Generation in Video Diffusion Transfo
        42633, -- 2501.04698 ConceptMaster: Multi-Concept Video Customization on Diffusion Transfor
        42652, -- 2501.05020 Perception-as-Control: Fine-grained Controllable Image Animation with
        42668, -- 2501.05379 Arc2Avatar: Generating Expressive 3D Avatars from a Single Image via I
        42693, -- 2501.05710 EmotiCrafter: Text-to-Emotional-Image Generation based on Valence-Arou
        42721, -- 2501.06187 Multi-subject Open-set Personalization in Video Generation
        42753, -- 2501.06655 Personalized Preference Fine-tuning of Diffusion Models
        42779, -- 2501.07070 Enhancing Image Generation Fidelity via Progressive Prompts
        42834, -- 2501.08225 FramePainter: Endowing Interactive Image Editing with Video Diffusion
        42849, -- 2501.08332 MangaNinja: Line Art Colorization with Precise Reference Following
        42857, -- 2501.08553 DynamicFace: High-Quality and Consistent Video Face Swapping using Com
        42907, -- 2501.09433 CaPa: Carve-n-Paint Synthesis for Efficient 4K Textured Mesh Generatio
        42913, -- 2501.09503 AnyStory: Towards Unified Single and Multiple Subject Personalization
        42932, -- 2501.09756 SynthLight: Portrait Relighting with Diffusion Model by Learning to Re
        42955, -- 2501.10021 X-Dyna: Expressive Dynamic Human Image Animation
        43021, -- 2501.11319 StyleSSP: Sampling StartPoint Enhancement for Training-free Diffusion-
        43028, -- 2501.11515 UltraFusion: Ultra High Dynamic Imaging using Exposure Fusion
        43059, -- 2501.12173 ComposeAnyone: Controllable Layout-to-Human Generation with Decoupled
        43060, -- 2501.12202 Hunyuan3D 2.0: Scaling Diffusion Models for High Resolution Textured 3
        43162, -- 2501.13787 Parameter-Efficient Fine-Tuning for Foundation Models
        43257, -- 2501.15407 Turn That Frown Upside Down: FaceID Customization via Cross-Training D
        43289, -- 2501.15891 Any2AnyTryon: Leveraging Adaptive Position Embeddings for Versatile Vi
        43591, -- 2502.01639 SliderSpace: Decomposing the Visual Capabilities of Diffusion Models
        43602, -- 2502.01720 Generating Multi-Image Synthetic Data for Text-to-Image Customization
        43655, -- 2502.02465 Towards Consistent and Controllable Image Synthesis for Face Editing
        43934, -- 2502.06527 CustomVideoX: 3D Reference Attention Driven Dynamic Adaptation for Zer
        44054, -- 2502.07784 MatSwap: Light-aware material transfers in images
        44062, -- 2502.07856 MRS: A Fast Sampler for Mean Reverting Diffusion based on ODE and SDE
        44150, -- 2502.09411 ImageRAG: Dynamic Image Retrieval for Reference-Guided Image Generatio
        44193, -- 2502.10059 RealCam-I2V: Real-World Image-to-Video Generation with Interactive Com
        44225, -- 2502.10458 I Think, Therefore I Diffuse: Enabling Multimodal In-Context Reasoning
        44273, -- 2502.11079 Phantom: Subject-consistent video generation via cross-modal alignment
        44511, -- 2502.13081 Personalized Image Generation with Deep Generative Models: A Decade Su
        44626, -- 2502.14247 Pandora3D: A Comprehensive Framework for High-Quality 3D Shape and Tex
        44914, -- 2502.17157 DICEPTION: A Generalist Diffusion Model for Visual Perceptual Tasks
        44947, -- 2502.17435 GCC: Generative Color Constancy via Diffusing a Color Checker
        45016, -- 2502.18417 GHOST 2.0: generative high-fidelity one shot transfer of heads
        45023, -- 2502.18461 K-LoRA: Unlocking Training-Free Fusion of Any Subject and Style LoRAs
        45027, -- 2502.18477 Recommendations Beyond Catalogs: Diffusion Models for Personalized Gen
        45136, -- 2502.19937 Image Referenced Sketch Colorization Based on Animation Creation Workf
        45156, -- 2502.20172 Multimodal Representation Alignment for Image Generation: Text-Image I
        45159, -- 2502.20220 Avat3r: Large Animatable Gaussian Reconstruction Model for High-fideli
        45160, -- 2502.20235 Attention Distillation: A Unified Approach to Visual Characteristics T
        45201, -- 2502.20650 Gungnir: Exploiting Stylistic Features in Images for Backdoor Attacks
        45276, -- 2503.00740 FaceShot: Bring Any Character into Life
        45289, -- 2503.00948 Extrapolating and Decoupling Image-to-Video Generation Models: Motion
        45663, -- 2503.06134 X2I: Seamless Integration of Multimodal Understanding into Diffusion T
        45676, -- 2503.06268 Get In Video: Add Anything You Want to the Video
        45689, -- 2503.06397 Removing Averaging: Personalized Lip-Sync Driven Characters Based on I
        45698, -- 2503.06505 DynamicID: Zero-Shot Multi-ID Image Personalization with Flexible Faci
        45725, -- 2503.06746 Color Alignment in Diffusion
        45758, -- 2503.07091 FaceID-6M: A Large-Scale, Open-Source FaceID Customization Dataset
        45776, -- 2503.07274 Efficient Distillation of Classifier-Free Guidance using Adapters
        45779, -- 2503.07307 AttenST: A Training-Free Attention-Driven Style Transfer Framework wit
        45780, -- 2503.07314 Automated Movie Generation via Multi-Agent CoT Planning
        45824, -- 2503.07703 Seedream 2.0: A Native Chinese-English Bilingual Image Generation Foun
        45860, -- 2503.08280 OminiControl2: Efficient Conditioning for Diffusion Transformers
        45875, -- 2503.08434 Bokeh Diffusion: Defocus Blur Control in Text-to-Image Diffusion Model
        45879, -- 2503.08478 NullFace: Training-Free Localized Face Anonymization
        45900, -- 2503.08650 MF-VITON: High-Fidelity Mask-Free Virtual Try-On with Minimal Input
        45937, -- 2503.09130 InteractEdit: Zero-Shot Editing of Human-Object Interactions in Images
        45941, -- 2503.09154 SwapAnyone: Consistent and Realistic Video Synthesis for Swapping Any
        45944, -- 2503.09277 UniCombine: Unified Multi-Conditional Combination with Diffusion Trans
        46004, -- 2503.09837 On the Limitations of Vision-Language Models in Understanding Image Tr
        46018, -- 2503.10125 Proxy-Tuning: Tailoring Multimodal Autoregressive Models for Subject-D
        46031, -- 2503.10287 MACS: Multi-source Audio-to-image Generation with Contextual Significa
        46032, -- 2503.10289 MaterialMVP: Illumination-Invariant Material Generation via Multi-view
        46038, -- 2503.10342 DreamInsert: Zero-Shot Image-to-Video Object Insertion from A Single I
        46044, -- 2503.10391 CINEMA: Coherent Multi-Subject Video Generation via MLLM-Based Guidanc
        46047, -- 2503.10406 RealGeneral: Unifying Visual Generation via Temporal In-Context Learni
        46061, -- 2503.10589 Long Context Tuning for Video Generation
        46066, -- 2503.10614 ConsisLoRA: Enhancing Content and Style Consistency for LoRA-based Sty
        46083, -- 2503.10637 Distilling Diversity and Control in Diffusion Models
        46153, -- 2503.11519 Exploring Typographic Visual Prompts Injection Threats in Cross-Modali
        46174, -- 2503.11937 Att-Adapter: A Robust and Precise Domain-Specific Multi-Attributes T2I
        46204, -- 2503.12545 PEBench: A Fictitious Dataset to Benchmark Machine Unlearning for Mult
        46208, -- 2503.12590 Personalize Anything for Free with Diffusion Transformer
        46213, -- 2503.12689 MagicID: Hybrid Preference Optimization for ID-Consistent and Dynamic-
        46230, -- 2503.12885 DreamRenderer: Taming Multi-Instance Attribute Control in Large-Scale
        46267, -- 2503.13434 BlobCtrl: A Unified and Flexible Framework for Element-level Image Gen
        46313, -- 2503.14151 Concat-ID: Towards Universal Identity-Preserving Video Synthesis
        46322, -- 2503.14275 Free-Lunch Color-Texture Disentanglement for Stylized Image Generation
        46342, -- 2503.14482 ICE-Bench: A Unified and Comprehensive Benchmark for Image Creating an
        46351, -- 2503.14503 The Power of Context: How Multimodality Improves Image Super-Resolutio
        46353, -- 2503.14505 MusicInfuser: Making Video Diffusion Listen and Dance
        46423, -- 2503.15686 Multi-focal Conditioned Latent Diffusion for Person Image Synthesis
        46446, -- 2503.16025 Single Image Iterative Subject-driven Generation and Editing
        46488, -- 2503.16418 InfiniteYou: Flexible Photo Recrafting While Preserving Your Identity
        46507, -- 2503.16611 A Recipe for Generating 3D Worlds From a Single Image
        46572, -- 2503.17671 ComfyGPT: A Self-Optimizing Multi-Agent System for Comprehensive Comfy
        46661, -- 2503.18860 HunyuanPortrait: Implicit Condition Control for Enhanced Portrait Anim
        46679, -- 2503.18950 Target-Aware Video Diffusion Models
        46707, -- 2503.19369 EfficientMT: Efficient Temporal Adaptation for Motion Transfer in Text
        46738, -- 2503.19824 AudCast: Audio-Driven Human Video Generation by Cascaded Diffusion Tra
        46739, -- 2503.19839 FireEdit: Fine-grained Instruction-based Image Editing via Region-awar
        46769, -- 2503.20188 Rethinking Vision-Language Model in Face Forensics: Multi-Modal Interp
        46785, -- 2503.20318 EditCLIP: Representation Learning for Image Editing
        46855, -- 2503.21541 LOCATEdit: Graph Laplacian Optimized Cross Attention for Localized Tex
        46876, -- 2503.21758 Lumina-Image 2.0: A Unified and Efficient Image Generative Framework
        46914, -- 2503.22179 High-Fidelity Diffusion Face Swapping with ID-Constrained Facial Condi
        46915, -- 2503.22194 ORIGEN: Zero-Shot 3D Orientation Grounding in Text-to-Image Generation
        47077, -- 2503.24387 Consistent Subject Generation via Contrastive Instantiated Concepts
        47081, -- 2504.00010 LayerCraft: Enhancing Text-to-Image Generation with CoT Reasoning and
        47203, -- 2504.02160 Less-to-More Generalization: Unlocking More Controllability by In-Cont
        47224, -- 2504.02436 SkyReels-A2: Compose Anything in Video Diffusion Transformers
        47246, -- 2504.02762 MD-ProjTex: Texturing 3D Shapes with Multi-Diffusion Projection
        47293, -- 2504.03536 HumanDreamer-X: Photorealistic Single-image Human Avatars Reconstructi
        47322, -- 2504.04010 DiTaiListener: Controllable High Fidelity Listener Video Generation wi
        47351, -- 2504.04753 CADCrafter: Generating Computer-Aided Design Models from Unconstrained
        47440, -- 2504.06632 PosterMaker: Towards High-Quality Product Poster Generation with Accur
        47443, -- 2504.06752 Compass Control: Multi Object Orientation Control for Text-to-Image Ge
        47481, -- 2504.07392 ID-Booth: Identity-consistent Face Generation with Diffusion Models
        47482, -- 2504.07405 FlexIP: Dynamic Control of Preservation and Personality for Customized
        47523, -- 2504.07960 VisualCloze: A Universal Image Generation Framework via Visual In-Cont
        47707, -- 2504.10822 IlluSign: Illustrating Sign Language Videos by Leveraging the Attentio
        47739, -- 2504.11389 VideoPanda: Video Panoramic Diffusion with Multi-view Attention
        47752, -- 2504.11478 Flux Already Knows -- Activating Subject-Driven Image Generation witho
        47809, -- 2504.12364 DMM: Building a Versatile Image Generation Model via Distillation-Base
        47810, -- 2504.12369 WORLDMEM: Long-term Consistent World Simulation with Memory
        47811, -- 2504.12395 InstantCharacter: Personalize Any Characters with a Scalable Diffusion
        47856, -- 2504.13078 Enhancing Person-to-Person Virtual Try-On with Multi-Garment Virtual T
        47870, -- 2504.13162 Personalized Text-to-Image Generation with Auto-Regressive Models
        47875, -- 2504.13176 IMAGGarment-1: Fine-Grained Garment Generation for Controllable Fashio
        47919, -- 2504.14011 Fashion-RAG: Multimodal Fashion Image Editing via Retrieval-Augmented
        47927, -- 2504.14202 Learning Joint ID-Textual Representation for ID-Preserving Image Synth
        47945, -- 2504.14509 DreamID: High-Fidelity and Fast diffusion-based Face Swapping via Trip
        47985, -- 2504.15009 Insert Anything: Image Insertion via In-Context Editing in DiT
        48012, -- 2504.15281 StyleMe3D: Stylization with Disentangled Priors by Multiple Encoders o
        48018, -- 2504.15397 MirrorVerse: Pushing Diffusion Models to Realistically Reflect the Wor
        48047, -- 2504.15958 FreeGraftor: Training-Free Cross-Image Feature Grafting for Subject-Dr
        48061, -- 2504.16080 From Reflection to Perfection: Scaling Inference-Time Optimization for
        48089, -- 2504.16915 DreamO: A Unified Framework for Image Customization
        48111, -- 2504.17502 RefVNLI: Towards Scalable Evaluation of Subject-driven Text-to-image G
        48123, -- 2504.17816 Subject-driven Video Generation via Disentangled Identity and Motion
        48193, -- 2504.19724 RepText: Rendering Visual Text via Replicating
        48244, -- 2504.20998 YoChameleon: Personalized Vision and Language Generation
        48273, -- 2504.21682 Visual Text Processing: A Comprehensive Review and Unified Evaluation
        48403, -- 2505.02567 Unified Multimodal Understanding and Generation Models: Advances, Chal
        48415, -- 2505.02823 MUSAR: Exploring Multi-Subject Customization from Single-Subject Datas
        48433, -- 2505.03097 Not All Parameters Matter: Masking Diffusion Models for Enhancing Gene
        48479, -- 2505.04320 Multi-turn Consistent Image Editing
        48644, -- 2505.07652 ShotAdapter: Text-to-Multi-Shot Video Generation with Diffusion Models
        48651, -- 2505.07747 Step1X-3D: Towards High-Fidelity and Controllable Generation of Textur
        48836, -- 2505.11131 One Image is Worth a Thousand Words: A Usability Preservable Text-Imag
        48948, -- 2505.12335 Is Artificial Intelligence Generated Image Detection a Solved Problem?
        48962, -- 2505.12486 Guiding Diffusion with Deep Geometric Moments: Balancing Fidelity and
        49562, -- 2505.17908 ComfyMind: Toward General-Purpose Generation via Tree-Based Planning a
        49610, -- 2505.18445 OmniConsistency: Learning Style-Agnostic Consistency from Paired Styli
        49680, -- 2505.19084 Jodi: Unification of Visual Generation and Understanding via Joint Mod
        49687, -- 2505.19114 CreatiDesign: A Unified Multi-Conditional Diffusion Transformer for Cr
        49692, -- 2505.19149 MIND-Edit: MLLM Insight-Driven Editing via Language-Vision Projection
        49849, -- 2505.20275 ImgEdit: A Unified Image Editing Dataset and Benchmark
        49861, -- 2505.20292 OpenS2V-Nexus: A Detailed Benchmark and Million-Scale Dataset for Subj
        49912, -- 2505.20914 Geometry-Editable and Appearance-Preserving Object Compositon
        49919, -- 2505.21062 Inverse Virtual Try-On: Generating Multi-Category Product-Style Images
        49926, -- 2505.21144 FastFace: Tuning Identity Preservation in Distilled Diffusion via Guid
        50099, -- 2505.23325 Dimension-Reduction Attack! Video Generative Models are Experts on Con
        50108, -- 2505.23462 LAFR: Efficient Diffusion-based Blind Face Restoration via Latent Code
        50148, -- 2505.23742 MAGREF: Masked Guidance for Any-Reference Video Generation
        50154, -- 2505.23758 LoRAShop: Training-Free Multi-Concept Image Generation and Editing wit
        50353, -- 2506.00996 Temporal In-Context Fine-Tuning for Versatile Control of Video Diffusi
        50440, -- 2506.02294 Improving Knowledge Distillation Under Unknown Covariate Shift Through
        50463, -- 2506.02620 FlexPainter: Flexible and Multi-View Consistent Texture Generation
        50492, -- 2506.03126 AnimeShooter: A Multi-Shot Animation Dataset for Reference-Guided Vide
        50529, -- 2506.03621 Negative-Guided Subject Fidelity Optimization for Zero-Shot Subject-Dr
        50648, -- 2506.05313 MARBLE: Material Recomposition and Blending in CLIP-Space
        50788, -- 2506.07848 PolyVivid: Vivid Multi-Subject Video Generation with Cross-Modal Inter
        50814, -- 2506.08006 Dreamland: Controllable World Creation with Simulator and Generative M
        50953, -- 2506.09916 Only-Style: Stylistic Consistency in Image Generation without Content
        50966, -- 2506.09984 InterActHuman: Multi-Concept Human Animation with Layout-Aligned Audio
        51379, -- 2506.18729 MuseControlLite: Multifunctional Music Generation with Lightweight Con
        51388, -- 2506.18871 OmniGen2: Exploration to Advanced Multimodal Generation
        51426, -- 2506.19741 Noise Consistency Training: A Native Approach for One-Step Generator i
        51513, -- 2506.21416 XVerse: Consistent Multi-Subject Control of Identity and Semantic Attr
        51613, -- 2507.00992 UniGlyph: Unified Segmentation-Conditioned Diffusion for Precise Visua
        51642, -- 2507.02321 Heeding the Inner Voice: Aligning ControlNet Training via Intermediate
        51728, -- 2507.05259 Beyond Simple Edits: X-Planner for Complex Instruction-Based Image Edi
        51742, -- 2507.05678 LiON-LoRA: Rethinking LoRA Fusion to Unify Controllable Spatial and Te
        51839, -- 2507.08396 Subject-Consistent and Pose-Diverse Text-to-Image Generation
        51908, -- 2507.11533 CharaConsist: Fine-Grained Consistent Character Generation
        52065, -- 2507.19058 ScenePainter: Semantically Consistent Perpetual 3D Scene Generation wi
        52156, -- 2508.01151 Personalized Safety Alignment for Text-to-Image Diffusion Models
        52249, -- 2508.04825 Voost: A Unified and Scalable Diffusion Transformer for Bidirectional
        52273, -- 2508.05769 Improving Masked Style Transfer using Blended Partial Convolution
        52292, -- 2508.06937 CannyEdit: Selective Canny Control and Dual-Prompt Guidance for Traini
        52308, -- 2508.07901 Stand-In: A Lightweight and Plug-and-Play Identity Control for Video G
        52311, -- 2508.07981 Omni-Effects: Unified and Spatially-Controllable Visual Effects Genera
        52321, -- 2508.08244 Cut2Next: Generating Next Shot via In-Context Tuning
        52355, -- 2508.09983 Story2Board: A Training-Free Approach for Expressive Storyboard Genera
        52377, -- 2508.10881 ToonComposer: Streamlining Cartoon Production with Generative Post-Key
        52384, -- 2508.11203 StyleMM: Stylized 3D Morphable Face Model via Text-Driven Aligned Imag
        52424, -- 2508.13632 OmniTry: Virtual Try-On Anything without Masks
        52479, -- 2508.16577 MV-RAG: Retrieval Augmented Multiview Diffusion
        52529, -- 2508.18966 USO: Unified Style and Subject-Driven Generation via Disentangled and
        52562, -- 2508.20586 FastFit: Accelerating Multi-Reference Virtual Try-On via Cacheable Dif
        52594, -- 2509.00428 Mixture of Global and Local Experts with Diffusion Transformer for Con
        52657, -- 2509.04434 Durian: Dual Reference-guided Portrait Animation with Attribute Transf
        52691, -- 2509.06818 UMO: Scaling Multi-Identity Consistency for Image Customization via Ma
        52796, -- 2509.21245 Hunyuan3D-Omni: A Unified Framework for Controllable Generation of 3D
        52879, -- 2509.15496 Lynx: Towards High-Fidelity Personalized Video Generation
        52969, -- 2509.21989 Mind-the-Glitch: Visual Correspondence for Detecting Inconsistencies i
        52985, -- 2509.22244 FlashEdit: Decoupling Speed, Structure, and Semantics for Precise Imag
        53046, -- 2509.21953 MultiCrafter: High-Fidelity Multi-Subject Generation via Spatially Dis
        53062, -- 2509.26231 IMG: Calibrating Diffusion Models via Implicit Multimodal Guidance
        53064, -- 2509.26391 MotionRAG: Motion Retrieval-Augmented Image-to-Video Generation
        53387, -- 2510.06679 DreamOmni2: Multimodal Instruction-based Editing and Generation
        53534, -- 2510.08532 Kontinuous Kontext: Continuous Strength Control for Instruction-based
        53594, -- 2510.14975 WithAnyone: Towards Controllable and ID Consistent Image Generation
        53644, -- 2510.15019 NANO3D: A Training-Free Approach for Efficient 3D Editing Without Mask
        53649, -- 2510.15868 LightsOut: Diffusion-based Outpainting for Enhanced Lens Flare Removal
        53683, -- 2510.16888 Uniworld-V2: Reinforce Image Editing with Diffusion Negative-aware Fin
        53794, -- 2510.20820 LayerComposer: Interactive Personalized T2I via Spatially-Aware Layere
        53862, -- 2510.20512 EchoDistill: Bidirectional Concept Distillation for One-Step Diffusion
        54008, -- 2510.24078 Beyond Objects: Contextual Synthetic Data Generation for Fine-Grained
        54243, -- 2511.10555 A Style is Worth One Code: Unlocking Code-to-Style Image Generation wi
        54286, -- 2511.16317 NaTex: Seamless Texture Generation as Latent Color Diffusion
        54301, -- 2511.17344 Loomis Painter: Reconstructing the Painting Process
        54354, -- 2511.20635 iMontage: Unified, Versatile, Highly Dynamic Many-to-many Image Genera
        54403, -- 2511.21691 Canvas-to-Image: Compositional Image Generation with Multimodal Contro
        54412, -- 2511.23199 Vision Bridge Transformer at Scale
        54417, -- 2511.18822 DiP: Taming Diffusion Models in Pixel Space
        54448, -- 2511.20614 The Consistency Critic: Correcting Inconsistencies in Generated Images
        54463, -- 2511.22989 MultiBanana: A Challenging Benchmark for Multi-Reference Text-to-Image
        54480, -- 2512.01686 DreamingComics: A Story Visualization Pipeline via Subject and Layout
        54497, -- 2512.02899 Glance: Accelerating Diffusion Models with 1 Sample
        54601, -- 2512.05965 EditThinker: Unlocking Iterative Reasoning for Any Image Editor
        54643, -- 2512.08294 OpenSubject: Leveraging Video-Derived Identity and Diversity Priors fo
        54685, -- 2512.09247 OmniPSD: Layered PSD Generation with Diffusion Transformer
        54722, -- 2512.10955 Omni-Attribute: Open-vocabulary Attribute Encoder for Visual Concept P
        54770, -- 2512.13674 Towards Interactive Intelligence for Digital Humans
        54781, -- 2512.13672 Directional Textual Inversion for Personalized Text-to-Image Generatio
        54795, -- 2512.12675 Scone: Bridging Composition and Distinction in Subject-Driven Image Ge
        54893, -- 2512.14884 Vibe Spaces for Creatively Connecting and Expressing Visual Concepts
        55034, -- 2512.22984 Reverse Personalization
        55036, -- 2512.22525 DreamOmni3: Scribble-based Editing and Generation
        55116, -- 2601.02785 DreamStyle: A Unified Framework for Video Stylization
        55121, -- 2601.03256 Muses: Designing, Composing, Generating Nonexistent Fantasy 3D Creatur
        55171, -- 2601.05124 Re-Align: Structured Reasoning-guided Alignment for In-Context Image G
        55323, -- 2601.10714 Alterbute: Editing Intrinsic Attributes of Objects in Images
        55387, -- 2601.14250 OmniTransfer: All-in-one Framework for Spatio-temporal Video Transfer
        55652, -- 2601.22680 Visual Personalization Turing Test
        55747, -- 2602.02914 FaceLinkGen: Rethinking Identity Leakage in Privacy-Preserving Face Re
        55774, -- 2602.04575 Vibe AIGC: A New Paradigm for Content Generation via Agentic Orchestra
        56556, -- 2603.07561 PureCC: Pure Learning for Text-to-Image Concept Customization
        56567, -- 2603.07236 HY-WU (Part I): An Extensible Functional Neural Memory Framework and A
        56625, -- 2603.10256 ID-LoRA: Identity-Driven Audio-Video Personalization with In-Context L
        56763, -- 2603.12743 MoKus: Leveraging Cross-Modal Knowledge Transfer for Knowledge-Aware C
        56766, -- 2603.14153 Garments2Look: A Multi-Reference Dataset for High-Fidelity Outfit-Leve
        56796, -- 2603.14152 SK-Adapter: Skeleton-Based Structural Control for Native 3D Generation
        56857, -- 2603.18524 3DreamBooth: High-Fidelity 3D Subject-Driven Video Generation Model
        56980, -- 2603.21937 MultiBind: A Benchmark for Attribute Misbinding in Multi-Subject Gener
        57135, -- 2603.26357 MPDiT: Multi-Patch Global-to-Local Transformer Architecture For Effici
        57202, -- 2603.27666 Gated Condition Injection without Multimodal Attention: Towards Contro
        57215, -- 2603.06679 MultiGen: Level-Design for Editable Multiplayer Worlds in Diffusion Ga
        57242, -- 2604.04911 SpatialEdit: Benchmarking Fine-Grained Image Spatial Editing
        57599, -- 2604.08537 Meta-learning In-Context Enables Training-Free Cross Subject Brain Dec
        57793, -- 2604.24351 Diffusion Templates: A Unified Plugin Framework for Controllable Diffu
        57813, -- 2604.27505 Leveraging Verifier-Based Reinforcement Learning in Image Editing
        57827, -- 2604.24953 ViPO: Visual Preference Optimization at Scale
        57832, -- 2605.00781 Map2World: Segment Map Conditioned Text to 3D World Generation
        58306, -- 2604.10617 Brain-Grasp: Graph-based Saliency Priors for Improved fMRI-based Visua
        58335, -- 2604.09817 NeuroFlow: Toward Unified Visual Encoding and Decoding from Neural Act
        58360, -- 2604.08915 Large-Scale Universal Defect Generation: Foundation Models and Dataset
        58642, -- 2604.03315 StoryBlender: Inter-Shot Consistent and Editable 3D Storyboard with Sp
        58796, -- 2603.27637 OPRO: Orthogonal Panel-Relative Operators for Panel-Aware In-Context I
        58814, -- 2603.22054 FontCrafter: High-Fidelity Element-Driven Artistic Font Creation with
        58825, -- 2603.26316 SALMUBench: A Benchmark for Sensitive Association-Level Multimodal Unl
        59074, -- 2603.20725 Premier: Personalized Preference Modulation with Learnable User Embedd
        59094, -- 2603.20012 Diffusion-Based Makeup Transfer with Facial Region-Aware Makeup Featur
        59190, -- 2603.17889 Identity as Presence: Towards Appearance and Voice Personalized Joint
        59505, -- 2603.12261 The Latent Color Subspace: Emergent Order in High-Dimensional Chaos
        59807, -- 2603.05971 Towards High-resolution and Disentangled Reference-based Sketch Colori
        59825, -- 2603.05769 Layer-wise Instance Binding for Regional and Occlusion Control in Text
        59837, -- 2603.05898 InnoAds-Composer: Efficient Condition Composition for E-Commerce Poste
        60087, -- 2603.00947 Mobile-VTON: High-Fidelity On-Device Virtual Try-On
        60143, -- 2509.23566 Towards Interpretable Visual Decoding with Attention to Brain Represen
        60237, -- 2602.22624 Instruction-based Image Editing with Planning, Reasoning, and Generati
        60309, -- 2602.21402 FlowFixer: Towards Detail-Preserving Subject-Driven Generation
        60344, -- 2602.20721 CleanStyle: Plug-and-Play Style Conditioning Purification for Text-to-
        60390, -- 2602.19575 ConceptPrism: Concept Disentanglement in Personalized Diffusion Models
        60394, -- 2602.19430 TherA: Thermal-Aware Visual-Language Prompting for Controllable RGB-to
        60455, -- 2602.18309 Multi-Level Conditioning by Pairing Localized Text and Sketch for Fash
        60662, -- 2602.14186 UniRef-Image-Edit: Towards Scalable and Consistent Multi-Reference Ima
        60765, -- 2602.12127 PosterOmni: Generalized Artistic Poster Creation via Task Distillation
        60793, -- 2602.12304 OmniCustom: Sync Audio-Video Customization Via Joint Audio-Video Gener
        61043, -- 2602.07564 SIGMA: Selective-Interleaved Generation with Multi-Attribute Tokens
        61078, -- 2602.06850 Rethinking Multi-Condition DiTs: Eliminating Redundant Attention via P
        61313, -- 2602.03753 Test-Time Conditioning with Representation-Aligned Visual Features
        61357, -- 2602.03220 PokeFusion Attention: Enhancing Reference-Free Style-Conditioned Gener
        61531, -- 2602.01306 DeCorStory: Gram-Schmidt Prompt Embedding Decorrelation for Consistent
        61727, -- 2601.22571 PerfGuard: A Performance-Aware Agent for Visual Content Generation
        61779, -- 2601.22094 RefAny3D: 3D Asset-Referenced Diffusion Models for Image Generation
        61887, -- 2601.20857 FreeFix: Boosting 3D Gaussian Splatting via Fine-Tuning-Free Diffusion
        62596, -- 2601.07833 Tuning-free Visual Effect Transfer across Videos
        62672, -- 2601.06965 Unified Personalized Understanding, Generating and Editing
        62770, -- 2601.05127 LooseRoPE: Content-aware Attention Manipulation for Semantic Harmoniza
        62799, -- 2601.04706 Forge-and-Quench: Enhancing Image Generation for Higher Fidelity in Un
        63219, -- 2512.23537 AnyMS: Bottom-up Attention Decoupling for Layout-guided and Training-f
        63234, -- 2512.23245 ASemConsist: Adaptive Semantic Feature Control for Training-Free Ident
        63538, -- 2412.09921 FaceShield: Defending Facial Image against Deepfake Threats
        63722, -- 2512.12963 SCAdapter: Content-Style Disentanglement for Diffusion Style Transfer
        63724, -- 2512.13247 STARCaster: Spatio-Temporal AutoRegressive Video Diffusion for Identit
        63753, -- 2512.12425 BokehDepth: Enhancing Monocular Depth Estimation through Bokeh Generat
        63757, -- 2512.12375 V-Warper: Appearance-Consistent Video Diffusion Personalization via Va
        63785, -- 2512.11715 EditMGT: Unleashing Potentials of Masked Generative Transformers in Im
        63859, -- 2512.10237 Multi-dimensional Preference Alignment by Conditioning Reward Itself
        63898, -- 2512.09417 DirectSwap: Mask-Free Cross-Identity Training and Benchmarking for Exp
        63925, -- 2512.08747 A Scalable Pipeline Combining Procedural 3D Graphics and Guided Diffus
        63987, -- 2512.07348 MICo-150K: A Comprehensive Dataset Advancing Multi-Image Composition
        64156, -- 2512.03964 Training for Identity, Inference for Controllability: A Unified Approa
        64256, -- 2512.01895 StyleYourSmile: Cross-Domain Face Retargeting Without Paired Multi-Sty
        64308, -- 2512.01236 PSR: Scaling Multi-Subject Personalized Image Generation with Pairwise
        64414, -- 2511.22940 One-to-All Animation: Alignment-Free Character Animation and Image Pos
        64562, -- 2511.19965 HiCoGen: Hierarchical Compositional Text-to-Image Generation in Diffus
        64593, -- 2511.19437 LumiTex: Towards High-Fidelity PBR Texture Generation with Illuminatio
        64607, -- 2511.19268 BideDPO: Conditional Image Generation with Simultaneous Text and Condi
        64636, -- 2511.18775 Rethinking Garment Conditioning in Diffusion-based Virtual Try-On
        64705, -- 2511.17979 FeRA: Frequency-Energy Constrained Routing for Effective Diffusion Ada
        64721, -- 2511.17501 Native 3D Editing with Full Attention
        64766, -- 2511.16666 SceneDesigner: Controllable Multi-Object Image Generation with 9-DoF P
        64830, -- 2511.15258 SplitFlux: Learning to Decouple Content and Style from a Single Image
        65299, -- 2511.05219 FreeControl: Efficient, Training-Free Structural Control via One-Step
        65353, -- 2511.04123 Text to Sketch Generation with Multi-Styles
        65463, -- 2511.01767 Wonder3D++: Cross-domain Diffusion for High-fidelity 3D Generation fro
        65541, -- 2511.00511 ID-Composer: Multi-Subject Video Synthesis with Hierarchical Identity
        65791, -- 2510.23515 FreeFuse: Multi-Subject LoRA Fusion via Auto Masking at Test Time
        65818, -- 2510.23023 UniAIDet: A Unified and Universal Benchmark for AI-Generated Image Con
        65823, -- 2510.22994 SceneDecorator: Towards Scene-Oriented Story Generation with Scene Pla
        65837, -- 2510.22810 MAGIC-Talk: Motion-aware Audio-Driven Talking Face Generation with Cus
        65848, -- 2510.22622 DeepfakeBench-MM: A Comprehensive Benchmark for Multimodal Deepfake De
        65952, -- 2510.20887 Preventing Shortcuts in Adapter Training via Providing the Shortcuts
        66093, -- 2510.18573 Kaleido: Open-Sourced Multi-Subject Reference Video Generation Model
        66317, -- 2510.14536 Exploring Image Representation with Decoupled Classical Visual Descrip
        66820, -- 2510.06827 StyleKeeper: Prevent Content Leakage using Negative Visual Query Guida
        66846, -- 2510.06469 SIGMA-GEN: Structure and Identity Guided Multi-subject Assembly for Im
        66891, -- 2510.05715 AgeBooth: Controllable Facial Aging and Rejuvenation via Diffusion Mod
        66940, -- 2510.04706 ID-Consistent, Precise Expression Generation with Blendshape-Guided Di
        67088, -- 2510.02291 Test-Time Anchoring for Discrete Diffusion Posterior Sampling
        67170, -- 2510.01347 Image Generation Based on Image Style Extraction
        67279, -- 2509.26641 Query-Kontext: An Unified Multimodal Model for Image Generation and Ed
        67315, -- 2509.26127 EchoGen: Generating Visual Echoes in Any Scene via Feed-Forward Subjec
        67357, -- 2509.25749 ART-VITON: Measurement-Guided Latent Diffusion for Artifact-Free Virtu
        67395, -- 2509.25180 DC-Gen: Post-Training Diffusion Acceleration with Deeply Compressed La
        67471, -- 2509.24514 Instruction Guided Multi Object Image Editing with Quantity and Layout
        67722, -- 2509.21938 SemanticControl: A Training-Free Approach for Handling Loosely Aligned
        68045, -- 2509.17120 Stencil: Subject-Driven Generation with Context Guidance
        68085, -- 2509.16630 Follow-Your-Emoji-Faster: Towards Efficient, Fine-Controllable, and Ex
        68285, -- 2509.13756 Controllable-Continuous Color Editing in Diffusion Model via Color Map
        68726, -- 2509.04379 SSGaussian: Semantic-Aware and Structure-Preserving 3D Style Transfer
        68752, -- 2509.03883 Human Motion Video Generation: A Survey
        68890, -- 2509.01181 FocusDPO: Dynamic Preference Optimization for Multi-Subject Personaliz
        68894, -- 2509.01107 FICGen: Frequency-Inspired Contextual Disentanglement for Layout-drive
        68960, -- 2509.00403 DevilSight: Augmenting Monocular Human Avatar Reconstruction through a
        69041, -- 2508.20615 EmoCAST: Emotional Talking Portrait via Emotive Text Description
        69431, -- 2508.14440 MUSE: Multi-Subject Unified Synthesis via Explicit Layout Semantic Exp
        69516, -- 2508.13065 Odo: Depth-Guided Diffusion for Identity-Preserving Body Reshaping
        69532, -- 2508.16644 CountLoop: Training-Free High-Instance Image Generation via Iterative
        69709, -- 2508.10171 SynSpill: Improved Industrial Spill Detection With Synthetic Data
        69758, -- 2508.09575 Dual Recursive Feedback on Generation and Appearance Latents for Pose-
        69803, -- 2508.08949 Lay2Story: Extending Diffusion Transformers for Layout-Togglable Story
        70010, -- 2508.05982 AnimateScene: Camera-controllable Animation in Any Scene
        70105, -- 2508.04559 One Model For All: Partial Diffusion for Unified Try-On and Try-Off in
        70214, -- 2508.03241 FFHQ-Makeup: Paired Synthetic Makeup Dataset with Facial Consistency A
        70293, -- 2508.02155 DreamPainter: Image Background Inpainting for E-commerce Scenarios
        70294, -- 2508.02151 AttriCtrl: Fine-Grained Control of Aesthetic Attribute Intensity in Di
        70400, -- 2508.00728 YOLO-Count: Differentiable Object Counting for Text-to-Image Generatio
        70486, -- 2508.03735 StorySync: Training-Free Subject Consistency in Text-to-Image Generati
        70532, -- 2507.22627 LOTS of Fashion! Multi-Conditioning for Image Generation via Sketch-Te
        70753, -- 2507.18633 Identifying Prompted Artist Names from Generated Images
        70942, -- 2507.15249 FreeCus: Free Lunch Subject-driven Customization in Diffusion Transfor
        70953, -- 2507.15085 Aesthetics is Cheap, Show me the Text: An Empirical Evaluation of Stat
        71015, -- 2507.13861 PositionIC: Unified Position and Identity Consistency for Image Custom
        71183, -- 2507.09747 BrainFLORA: Uncovering Brain Concept Representation via Multimodal Neu
        71245, -- 2507.08380 From Enhancement to Understanding: Build a Generalized Bridge for Low-
        71393, -- 2507.04599 QR-LoRA: Efficient and Disentangled Fine-tuning via QR Decomposition f
        71408, -- 2507.04349 TTS-CtrlNet: Time varying emotion aligned text-to-speech generation wi
        71503, -- 2507.01926 IC-Custom: Diverse Image Customization via In-Context Learning
        71598, -- 2506.24085 Imagine for Me: Creative Conceptual Blending of Real Images and Text v
        71635, -- 2506.23361 OmniVCus: Feedforward Subject-driven Video Customization with Multimod
        71712, -- 2506.21270 Video Virtual Try-on with Conditional Diffusion Transformer Inpainter
        71720, -- 2506.20879 MultiHuman-Testbench: Benchmarking Image Generation for Multiple Human
        71843, -- 2506.16852 Controllable and Expressive One-Shot Video Head Swapping
        71917, -- 2506.17301 FramePrompt: In-context Controllable Animation with Zero Structural Ch
        71919, -- 2506.15742 FLUX.1 Kontext: Flow Matching for In-Context Image Generation and Edit
        71994, -- 2506.12198 ViSTA: Visual Storytelling using Multi-modal Adapters for Text-to-Imag
        72073, -- 2506.09612 Consistent Story Generation: Unlocking the Potential of Zigzag Samplin
        72181, -- 2506.06802 Training-Free Diffusion Framework for Stylized Image Generation with I
        72213, -- 2506.05843 FontAdapter: Instant Font Adaptation in Visual Text Generation
        72286, -- 2506.05407 PCEvolve: Private Contrastive Evolution for Synthetic Dataset Generati
        72341, -- 2506.02560 DCI: Dual-Conditional Inversion for Boosting Diffusion-Based Image Edi
        72360, -- 2506.02221 Diff2Flow: Training Flow Matching Models via Diffusion Model Alignment
        72369, -- 2506.01949 IMAGHarmony: Controllable Image Editing with Consistent Object Quantit
        72919, -- 2505.14671 UniCTokens: Boosting Personalized Understanding and Generation via Uni
        73119, -- 2505.06537 ProFashion: Prototype-guided Fashion Video Generation with Multiple Re
        73163, -- 2505.04656 MeshGen: Generating PBR Textured Mesh with Render-Enhanced Auto-Encode
        73242, -- 2504.21476 GarmentDiffusion: 3D Garment Sewing Pattern Generation with Multimodal
        73604, -- 2504.06861 EIDT-V: Exploiting Intersections in Diffusion Trajectories for Model-A
        73610, -- 2504.06778 Controllable Automatic Foley Artist
        73761, -- 2504.01008 IntrinsiX: High-Quality PBR Generation using Image Priors
        73894, -- 2503.19011 RomanTex: Decoupling 3D-aware Rotary Positional Embedded Multi-Attenti
        74045, -- 2503.12652 UniVG: A Generalist Diffusion Model for Unified Image Generation and E
        74302, -- 2503.02399 VisAgent: Narrative-Preserving Story Visualization Framework
        74310, -- 2503.02206 Language-Guided Visual Perception Disentanglement for Image Quality As
        74349, -- 2503.01294 Fine-Grained Controllable Apparel Showcase Image Generation via Garmen
        74419, -- 2502.20577 InstaFace: Identity-Preserving Facial Editing with Single Image Infere
        74426, -- 2502.20376 Tight Inversion: Image-Conditioned Inversion for Real Image Editing
        74738, -- 2502.08234 Learning Human Skill Generators at Key-Step Levels
        74955, -- 2502.06805 Efficient Diffusion Models: A Survey
        75083, -- 2501.15253 Dual Frequency Branch Framework with Reconstructed Sliding Windows Att
        75491, -- 2412.09844 Real-time Identity Defenses against Malicious Personalization of Diffu
        75599, -- 2412.03685 Sprite Sheet Diffusion: Generate Game Character for Animation
        75605, -- 2412.03255 DynamicControl: Adaptive Condition Selection for Improved Text-to-Imag
        75644, -- 2412.00397 DreamDance: Animating Human Images by Enriching 3D Geometry Cues from
        75729, -- 2411.16713 Conditional Text-to-Image Generation with Reference Guidance
        76462, -- 2409.02543 StyleTokenizer: Defining Image Style by a Single Instance for Controll
        76571, -- 2408.09397 Combo: Co-speech holistic 3D human motion generation and efficient cus
        76833, -- 2407.02329 MIGC++: Advanced Multi-Instance Generation Controller for Image Synthe
        77117, -- 2406.00773 Diffusion Tuning: Transferring Diffusion Models via Chain of Forgettin
        77651, -- 2403.07721 Visual Decoding and Reconstruction via EEG Embeddings with Guided Diff
        77857, -- 2402.02242 Parameter-Efficient Fine-Tuning for Pre-Trained Vision Models: A Surve
        82847, -- 2605.05204 D-OPSD: On-Policy Self-Distillation for Continuously Tuning Step-Disti
        82954, -- 2605.07940 Delta-Adapter: Scalable Exemplar-Based Image Editing with Single-Pair
        83237, -- 2605.12013 L2P: Unlocking Latent Potential for Pixel Generation
        83317, -- 2605.10302 Follow the Mean: Reference-Guided Flow Matching
        83449, -- 2605.19995 CogOmniControl: Reasoning-Driven Controllable Video Generation via Cre
        83767, -- 2605.08129 Towards Customized Multimodal Role-Play
        83769, -- 2605.25191 Injecting Image Guidance into Text-Conditioned Diffusion Models at Inf
        83818, -- 2605.26111 Squeezing Capacity from Multimodal Large Language Models for Subject-d
        83917, -- 2605.25378 CollectionLoRA: Collecting 50 Effects in 1 LoRA via Multi-Teacher On-P
        84052, -- 2506.23690 SynMotion: Semantic-Visual Adaptation for Motion Customized Video Gene
        84205, -- 2511.17844 Less is More: Data-Efficient Adaptation for Controllable Text-to-Video
        84275, -- 2511.22287 Match-and-Fuse: Consistent Generation from Unstructured Image Sets
        84280, -- 2511.22690 Ar2Can: An Architect and an Artist Leveraging a Canvas for Multi-Human
        84323, -- 2512.02781 LumiX: Structured and Coherent Text-to-Intrinsic Generation
        84370, -- 2512.08826 CARLoS: Retrieval via Concise Assessment Representation of LoRAs at Sc
        84378, -- 2512.10669 Learning by Analogy: A Causal Framework for Compositional Generalizati
        84381, -- 2512.10943 AlcheMinT: Fine-grained Temporal Control for Multi-Reference Consisten
        84402, -- 2512.14236 Elastic3D: Controllable Stereo Video Conversion with Guided Latent Dec
        84422, -- 2512.18312 MatE: Material Extraction from Single-Image via Geometric Prior
        84473, -- 2601.09265 GaussianFluent: Gaussian Simulation for Dynamic Scenes with Mixed Mate
        84494, -- 2601.20511 Say Cheese! Detail-Preserving Portrait Collection Generation via Natur
        84529, -- 2602.18873 BiMotion: B-spline Motion for Text-guided Dynamic 3D Character Generat
        84618, -- 2602.22150 CoLoGen: Progressive Learning of Concept-Localization Duality for Unif
        84782, -- 2603.06688 Narrative Weaver: Towards Controllable Long-Range Visual Consistency w
        84907, -- 2603.14209 ChArtist: Generating Pictorial Charts with Unified Spatial and Subject
        84977, -- 2603.19121 CustomTex: High-fidelity Indoor Scene Texturing via Multi-Reference Cu
        85025, -- 2603.21295 Text-Image Conditioned 3D Generation
        85223, -- 2604.00849 Disentangling to Re-couple: Resolving the Similarity-Controllability P
        85283, -- 2604.05039 ID-Sim: An Identity-Focused Similarity Metric
        85342, -- 2604.10485 UDAPose: Unsupervised Domain Adaptation for Low-Light Human Pose Estim
        85363, -- 2604.12309 Towards Realistic and Consistent Orbital Video Generation via 3D Found
        85408, -- 2604.17195 DreamShot: Personalized Storyboard Synthesis with Video Diffusion Prio
        85499, -- 2605.02393 FEAT: Fashion Editing and Try-On from Any Design
        85559, -- 2605.14708 StyleTextGen: Style-Conditioned Multilingual Scene Text Generation
        86020, -- 2505.07344 Generative Pre-trained Autoregressive Diffusion Transformer
        86300, -- 2410.18804 Fast constrained sampling in pre-trained diffusion models
        86559, -- 2503.19034 Color Conditional Generation with Sliced Wasserstein Guidance
        86774, -- 2506.14549 DreamLight: Towards Harmonious and Consistent Image Relighting
        87113, -- 2510.12119 ImageSentinel: Protecting Visual Datasets from Unauthorized Retrieval-
        87243, -- 2510.15194 Salient Concept-Aware Generative Data Augmentation
        87452, -- 2507.12318 Compositional Discrete Latent Code for High Fidelity, Productive Diffu
        87549, -- 2507.20721 AIComposer: Any Style and Content Image Composition via Feature Integr
        87684, -- 2504.20042 CompleteMe: Reference-based Human Image Completion
        87742, -- 2507.03257 LACONIC: A 3D Layout Adapter for Controllable Image Creation
        87813, -- 2509.07920 ScoreHOI: Physically Plausible Reconstruction of Human-Object Interact
        87845, -- 2412.14580 DiffSim: Taming Diffusion Models for Evaluating Visual Similarity
        87863, -- 2508.14461 Ouroboros: Single-step Diffusion Models for Cycle-consistent Forward a
        87885, -- 2504.13206 DuoLoRA : Cycle-consistent and Rank-disentangled Content-Style Persona
        87890, -- 2411.17784 HypDAE: Hyperbolic Diffusion Autoencoders for Hierarchical Few-shot Im
        87894, -- 2411.18068 PersonaCraft: Personalized and Controllable Full-Body Multi-Human Scen
        87977, -- 2508.08556 Unlocking the Potential of Diffusion Priors in Blind Face Restoration
        88027, -- 2504.10434 Anchor Token Matching: Implicit Structure Locking for Training-free AR
        88144, -- 2503.15877 Repurposing 2D Diffusion Models with Gaussian Atlas for 3D Generation
        88159, -- 2507.04243 Domain Generalizable Portrait Style Transfer
        88208, -- 2506.22531 Preserve Anything: Controllable Image Synthesis with Object Preservati
        88257, -- 2504.08291 DreamFuse: Adaptive Image Fusion with Diffusion Transformer
        88273, -- 2410.09879 TextMaster: A Unified Framework for Realistic Text Editing via Glyph-S
        88396, -- 2505.23186 HiGarment: Cross-modal Harmony Based Diffusion Model for Flat Sketch t
        88498, -- 2510.05660 Teleportraits: Training-Free People Insertion into Any Scene
        89065, -- 2410.02483 Event-Customized Image Generation
        89440, -- 2505.12427 DragLoRA: Online Optimization of LoRA Adapters for Drag-based Image Ed
        89638, -- 2503.07416 TimeStep Master: Asymmetrical Mixture of Timestep LoRA Experts for Ver
        89839, -- 2406.08337 WMAdapter: Adding WaterMark Control to Latent Diffusion Models
        90150, -- 2503.17197 FreeUV: Ground-Truth-Free Realistic Facial UV Texture Recovery via Cro
        90157, -- 2505.06068 Noise-Consistent Siamese-Diffusion for Medical Image Synthesis and Seg
        90189, -- 2412.06143 Precise, Fast, and Low-cost Concept Erasure in Value Space: Orthogonal
        90191, -- 2503.16065 Shining Yourself: High-Fidelity Ornaments Virtual Try-on with Diffusio
        90216, -- 2505.01428 Multi-party Collaborative Attention Control for Image Customization
        90249, -- 2503.00861 Zero-Shot Head Swapping in Real-World Scenarios
        90258, -- 2405.12661 EmoEdit: Evoking Emotions through Image Manipulation
        90264, -- 2503.16630 TriTex: Learning Texture from a Single Mesh via Triplane Semantic Feat
        90282, -- 2503.15406 Visual Persona: Foundation Model for Full-Body Human Customization
        90334, -- 2412.11519 LineArt: A Knowledge-guided Training-free High-quality Appearance Tran
        90336, -- 2502.07802 Movie Weaver: Tuning-Free Multi-Concept Video Personalization with Anc
        90337, -- 2503.10112 MoEdit: On Learning Quantity Perception for Multi-object Image Editing
        90350, -- 2404.03632 Reference-Based 3D-Aware Image Editing with Triplanes
        90427, -- 2503.11143 GaussianIP: Identity-Preserving Realistic 3D Human Generation via Huma
        90712, -- 2503.14485 Lux Post Facto: Learning Portrait Performance Relighting with Conditio
        90730, -- 2501.08279 SmartEraser: Remove Anything from Images using Masked-Region Guidance
        90751, -- 2503.01115 WeGen: A Unified Model for Interactive Multimodal Generation as We Cha
        90770, -- 2411.15843 Unveil Inversion and Invariance in Flow Transformer for Versatile Imag
        90869, -- 2412.05538 Not Just Text: Uncovering Vision Modality Typographic Threats in Image
        90975, -- 2503.04501 IMFine: 3D Inpainting via Geometry-guided Multi-view Refinement
        92087, -- 2501.15878 Slot-Guided Adaptation of Pre-trained Diffusion Models for Object-Cent
        93208, -- 2602.07495 Learning Brain Representation with Hierarchical Visual Embeddings
        93411, -- 2503.01122 ACCORD: Alleviating Concept Coupling through Dependence Regularization
        93869, -- 2601.11675 Generating metamers of human scene understanding
        94027, -- 2602.01864 Trust but Verify: Adaptive Conditioning for Reference-Based Diffusion
        94049, -- 2602.10552 MindPilot: Closed-loop Visual Stimulation Optimization for Brain Modul
        94351, -- 2510.14553 Consistent Text-to-Image Generation via Scene De-Contextualization
        94504, -- 2602.18752 Optimizing ID Consistency in Multimodal Large Models: Facial Restorati
        94699, -- 2508.15773 Scaling Group Inference for Diverse and High-Quality Generation
        94783, -- 2602.08388 Geometric Image Editing via Effects-Sensitive In-Context Inpainting wi
        94986, -- 2505.18612 Mod-Adapter: Tuning-Free and Versatile Multi-concept Personalization v
        95035, -- 2504.13109 UniEdit-Flow: Unleashing Inversion and Editing in the Era of Flow Mode
        96622, -- 2602.11875 DiffPlace: Street View Generation Via Place-Controllable Diffusion Mod
        98322, -- 2606.13872 Avatar V: Scaling Video-Reference Avatar Video Generation
        98482, -- 2606.15158 RefGC-SR^2: Reference-guided Generated Content Super-Resolution and Re
        98540, -- 2606.20506 FreeStyle: Free Control of Style-Content Dual-Reference Generation fro
        98586, -- 2606.20556 Thinking in Boxes: 3D Editing in Real Images Made Easy
        98722, -- 2606.23514 Arbor: Explicit Geometric Conditioning for Controllable 3D Asset Gener
        98817, -- 2606.21661 UnityShots: Memory-Driven Multi-Shot Audio-Video Generation with Bound
        99004, -- 2606.30968 PhotoQuilt: Training-Free Arbitrary-Resolution Photomosaics via Bootst
        99055, -- 2607.00407 Personalization as Inverse Planning: Learning Latent Design Intents fo
        99111, -- 2607.01803 PixGS: Pixel-Space Diffusion for Direct 3D Gaussian Splat Generation
        99729, -- 2606.13496 Budget-Constrained Step-Level Diffusion Caching
        99763, -- 2512.20014 Bring My Cup! Personalizing Vision-Language-Action Models with Visual
        100353, -- 2605.21207 PGC: Peak-Guided Calibration for Generalizable AI-Generated Image Dete
        101373, -- 2602.02388 Personalized Image Generation via Human-in-the-loop Bayesian Optimizat
        101450, -- 2511.13108 DGS-Net: Distillation-Guided Gradient Surgery for CLIP Fine-Tuning in
        101736, -- 2605.15921 AdaEraser: Training-Free Object Removal via Adaptive Attention Suppres
        102185, -- 2603.06981 Diffusion Controller: Framework, Algorithms and Parameterization
        103947, -- 2607.11885 Latent-Identity Tuning in Text-to-Image Personalization Models
        104000, -- 2607.05382 Search Beyond What Can Be Taught: Evolving the Knowledge Boundary in A
        104831, -- 2606.22945 Controllable Texture Tiling via Diffusion Transformers with Transforme
        105983, -- 2605.28657 DEMON: Diffusion Engine for Musical Orchestrated Noise
        106021, -- 2607.29025 Evaluation-Verification Reward for Consistent Multi-Reference Image Ed
        107158, -- 2507.10470 RefSTAR: Blind Face Image Restoration with Reference Selection, Transf
        107203, -- 2509.04446 Plot’n Polish: Zero-Shot Story Visualization and Disentangled Editing
        107850, -- 2503.07253 AnomalyPainter: Vision-Language-Diffusion Synergy for Realistic and Di
        108698, -- 2605.13857 MoZoo:Unleashing Video Diffusion power in animal fur and muscle simula
        108787, -- 2605.12305 Images in Sentences: Scaling Interleaved Instructions for Unified Visu
        108788, -- 2605.12119 MoCam: Unified Novel View Synthesis via Structured Denoising Dynamics
        109037, -- 2506.22007 RoboEnvision: A Long-Horizon Video Generation Model for Multi-Task Rob
        109065, -- 2608.06751 Beyond Starry Night: Shortcut-Aware Control-State Planning for Artist-
        109522, -- 2608.20336 WithEveryone: Unified Planning and Identity Grounding for Group Image
        109907, -- 2412.03315 Geometry-Guided Cross-View Diffusion for One-to-Many Cross-View Image
        112467, -- 2407.10833 MoE-DiffIR: Task-customized Diffusion Priors for Universal Compressed
        112720, -- 2403.15033 Toward Tiny and High-quality Facial Makeup with Data Amplify Learning
        112976, -- 2405.14582 PoseCrafter: One-Shot Personalized Video Synthesis Following Flexible
        114015, -- 2609.06758 Agentic Visual Generation: From Generative Models to Agentic Control
        115766, -- 2402.00627 CapHuman: Capture Your Moments in Parallel Universes
        116338, -- 2401.02847 Generating Non-Stationary Textures using Self-Rectification
        116915, -- 2403.05239 Towards Effective Usage of Human-Centric Priors in Diffusion Models fo
        117375, -- 2606.31764 NURBS Splatting: A Unified Differentiable Rendering Framework for Vect
        117412, -- 2603.22972 WorldMesh: Generating Navigable Multi-Room 3D Scenes via Mesh-Conditio
        117537, -- 2601.05722 Rotate Your Character: Revisiting Video Diffusion Models for High-Qual
        117557, -- 2606.27584 CoIn: Comprehensive 2D-3D Inpainting with Gaussian Splatting Guidance
        117562, -- 2605.16990 DreamEdit3D: Personalization of Multi-View Diffusion Models for 3D Edi
        118114, -- 2607.04484 TrustCLIP: Learning Private Visual Features via Adversarial Reconstruc
        118136, -- 2607.14595 MagicPrompt: Ultra-Lightweight Prompt Tuning for Video Generation
        118177, -- 2604.07753 Symbiotic-MoE: Unlocking the Synergy between Generation and Understand
        118240, -- 2512.02453 ClusterStyle: Modeling Intra-Style Diversity with Prototypical Cluster
        118372, -- 2604.10954 FineEdit: Fine-Grained Image Edit with Bounding Box Guidance
        118383, -- 2607.04691 From Open Loop to Closed Loop: A Test-Time Iterative Optimization Fram
        118389, -- 2607.22101 InnoText: A Unified Model for Visual Text Generation and Editing
        118395, -- 2512.12598 Setting the Stage: Text-Driven Scene-Consistent Image Generation
        118422, -- 2603.08090 DSH-Bench: A Difficulty- and Scenario-Aware Benchmark with Hierarchica
        118548, -- 2603.26866 LACON: Training Text-to-Image Model from Uncurated Data
        118578, -- 2603.18466 Recolour What Matters: Region-Aware Colour Editing via Token-Level Dif
        118587, -- 2604.17850 UniCSG: Unified High-Fidelity content-constrained style-driven generat
        118590, -- 2607.04677 AnyStyle: A Single LoRA is Sufficient for Image-Guided Style Transfer
        118597, -- 2607.06162 High-Resolution Artwork Outpainting with Global Blueprint Guidance and
        118623, -- 2606.31683 Histogram-constrained Image Generation
        118720, -- 2606.28696 COMPASS: Grounding Composition-Intent Guidance in Unified Multimodal M
        118861, -- 2608.04394 Free-Lunch Augmentation by Revisiting Diffusion-Based Data Generation
        119032, -- 2604.26520 3D-LENS: A 3D Lifting-based Elevated Novel-view Synthesis method for S
        119180, -- 2603.12864 Composing Driving Worlds through Disentangled Control for Adversarial
        119241, -- 2606.25465 EchoStyle: Unlocking High-Fidelity Video Stylization with Reverse Data
        119263, -- 2606.26916 PhysRAG: Enhancing Physics-Awareness in Video Generation via Retrieval
        119286, -- 2602.11117 HairWeaver: Few-Shot Photorealistic Hair Motion Synthesis with Sim-to-
        119420, -- 2607.21592 Unified Video Dense Prediction from Disjoint Data
        119486, -- 2607.12042 SymbOmni: Evolving Agentic Omni Models via Symbolic Concept Learning
        119856, -- 2508.02004 Devil is in the Detail: Towards Injecting Fine Details of Image Prompt
        119880, -- 2503.08269 Adv-CPG: A Customized Portrait Generation Framework with Facial Advers
        119990, -- 2504.01603 ATA: Adaptive Transformation Agent for Text-Guided Subject-Position Va
        120046, -- 2408.06047 BooW-VTON: Boosting In-the-Wild Virtual Try-On via Mask-Free Pseudo Da
        120047, -- 2512.14542 HiFi-Portrait: Zero-shot Identity-preserved Portrait Generation with H
        120607, -- 2506.16960 Visual-Instructed Degradation Diffusion for All-in-One Image Restorati
        120758, -- 2602.00267 PLACID: Identity-Preserving Multi-Object Compositing via Video Diffusi
        121184, -- 2602.21273 StoryTailor:A Zero-Shot Pipeline for Action-Rich Multi-Subject Visual
        121347, -- 2603.08147 MV-Fashion: Towards Enabling Virtual Try-On and Size Estimation with M
        121895, -- 2507.04678 ChangeBridge: Spatiotemporal Image Generation with Multimodal Controls
        122077, -- 2609.20816 Paint-Anything: Unified Any-Color Control for Image Generation and Edi
        122178, -- 2609.27901 All modalities are equal, but video is more equal: Closing the Cross-A
        122582, -- 2610.00737 Personalized Image Generation with Reasoning and Reflection
        122935, -- 2609.38680 ReGain: Restoring Subject Fidelity in Personalization on Synthetic Ima
        123251, -- 2610.00359 Diffusion Editing with Soft Mask: Pixel Level Redo of Image and Video
        123408, -- 2604.01973 NearID: Identity Representation Learning via Near-identity Distractors
        123573, -- 2610.20731 WorldCast: Exploring Intelligent Visual Generation in World State Pred
        123784, -- 2610.26851 Manga2Animate: An Agentic Framework for Faithful Manga Animation with
        124963, -- 2606.06120 Diff-CA: Separating Common and Salient Factors with Diffusion Models
        127020, -- 2610.11857 Pose-Free Feed-Forward 3D Inpainting via Learnable Mask Attention and
        127025, -- 2609.38136 CLeaR: A Unified Framework for Resolving the Leakage–Degradation Dilem
        127087, -- 2607.02220 DetailAnywhere: Fashion Detail Generation via Cross-Modal Feature Alig
        127879, -- 2605.15196 RefDecoder: Enhancing Visual Generation with Conditional Video Decodin
        128843, -- 2610.16892 Barycentric Guidance: Turning Foundation Image Editors into Continuous
        129666, -- 2602.05339 Consistency-Preserving Concept Erasure via Unsafe–Safe Pairing and Dir
        129963, -- 2605.22133 Atom-level Protein Representation Learning Improves Protein Structure
        130012, -- 2605.12088 UniCustom: Unified Visual Conditioning for Multi-reference Image Gener
        130214, -- 2503.06684 PixelPonder: Dynamic Patch Adaptation for Enhanced Multi-Conditional T
        130238, -- 2606.11670 ARGUS: Stacked Multi-View Identity Mosaic Injection for Subject-Preser
        130997, -- 2606.13768 CineOrchestra: Unified Entity-Centric Conditioning for Cinematic Video
        131098, -- 2605.16732 DiRotQ: Rotation-Aware Quantization for 4-bit Diffusion Transformers
        131542, -- 2610.29003 T-DIG: Text-Conditioned Diversity for Image Generation
        131556, -- 2610.35684 OmniShowcase: Omnidirectional Subject-Consistent Video Generation from
        131696, -- 2610.36545 FrameForge: Harnessing Priors of Video Foundation Models for Unified I
        131944  -- 2610.40119 SynthFaces: Balanced Large Scale Human Dataset
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
        20631, -- 2309.10740 ConsistencyTTA: Accelerating Diffusion-Based Text-to-Audio Generation
        21507, -- 2310.04378 Latent Consistency Models: Synthesizing High-Resolution Images with Fe
        23134, -- 2311.05556 LCM-LoRA: A Universal Stable-Diffusion Acceleration Module
        23906, -- 2311.17042 Adversarial Diffusion Distillation
        24654, -- 2312.06971 CCM: Adding Conditional Controls to Text-to-Image Consistency Models
        24775, -- 2312.08887 SpeedUpNet: A Plug-and-Play Adapter Network for Accelerating Text-to-I
        24794, -- 2312.09109 VideoLCM: Video Latent Consistency Model
        25652, -- 2401.05252 PIXART-δ: Fast and Controllable Image Generation with Latent Consisten
        26587, -- 2402.00769 AnimateLCM: Computation-Efficient Personalized Style Video Generation
        26860, -- 2402.03501 An Inpainting-Infused Pipeline for Attire and Background Replacement
        28192, -- 2402.19159 Trajectory Consistency Distillation: Improved Latent Consistency Disti
        28359, -- 2403.02084 ResAdapter: Domain Consistent Resolution Adapter for Diffusion Models
        28825, -- 2403.09055 SemanticDraw: Towards Real-Time Interactive Content Creation from Imag
        28972, -- 2403.11027 Reward Guided Latent Consistency Distillation
        29385, -- 2403.16024 A Unified Module for Accelerating STABLE-DIFFUSION: LCM-LORA
        29955, -- 2404.03620 LCM-Lookahead for Encoder-based Text-to-Image Personalization
        30081, -- 2404.05595 UniFL: Improve Latent Diffusion Model via Unified Feedback Learning
        30495, -- 2404.11925 EdgeFusion: On-Device Text-to-Image Generation
        30680, -- 2404.14700 FlashSpeech: Efficient Zero-Shot Speech Synthesis
        30946, -- 2404.19759 MotionLCM: Real-time Controllable Motion Generation via Latent Consist
        31943, -- 2405.18407 Phased Consistency Models
        32572, -- 2406.05768 TLCM: Training-efficient Latent Consistency Model for Image Generation
        32876, -- 2406.09293 StableMaterials: Enhancing Diversity in Material Generation via Semi-S
        33074, -- 2406.11202 Consistency^2: Consistent and Fast 3D Painting with Latent Consistency
        35719, -- 2408.05492 ZePo: Zero-Shot Portrait Stylization with Faster Sampling
        37002, -- 2409.11367 OSV: One Step is Enough for High-Quality Image to Video Generation
        40822, -- 2412.01271 MuLan: Adapting Multilingual Diffusion Models for Hundreds of Language
        41804, -- 2412.13479 Real-time One-Step Diffusion-based Expressive Portrait Videos Generati
        43569, -- 2502.01441 Improved Training Technique for Latent Consistency Models
        43640, -- 2502.02215 InterLCM: Low-Quality Images as Intermediate States of Latent Consiste
        49677, -- 2505.19063 Training-free Stylized Text-to-Image Generation with Fast Inference
        49988, -- 2505.21960 One-Way Ticket:Time-Independent Unified Encoder for Distilling Text-to
        52614, -- 2509.01624 Q-Sched: Pushing the Boundaries of Few-Step Diffusion Models with Quan
        57876, -- 2604.23584 Identity-Decoupled Anonymization for Visual Evidence in Multi-modal Re
        59160, -- 2603.20304 Transferable Multi-Bit Watermarking Across Frozen Diffusion Models via
        70203, -- 2508.03357 GL-LCM: Global-Local Latent Consistency Models for Fast High-Resolutio
        89212, -- 2506.18251 Morse: Dual-Sampling for Lossless Acceleration of Diffusion Models
        90141, -- 2503.09122 Training Data Provenance Verification: Did Your Model Use Synthetic Da
        117367  -- external ConTiCoM-3D: A Continuous-Time Consistency Model for 3D Point Cloud Ge
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
        15466, -- 2305.07015 Exploiting Diffusion Prior for Real-World Image Super-Resolution
        15694, -- 2305.10722 Discffusion: Discriminative Diffusion Models as Few-shot Vision and La
        16277, -- 2305.15798 BK-SDM: A Lightweight, Fast, and Cheap Version of Stable Diffusion
        17125, -- 2306.04744 WOUAF: Weight Modulation for User Attribution and Fingerprinting in Te
        19894, -- 2308.15070 DiffBIR: Towards Blind Image Restoration with Generative Diffusion Pri
        20332, -- 2309.06380 InstaFlow: One Step is Enough for High-Quality Diffusion-Based Text-to
        20689, -- 2309.11497 FreeU: Free Lunch in Diffusion U-Net
        21444, -- 2310.03420 FreeReg: Image-to-Point Cloud Registration Leveraging Pretrained Diffu
        23396, -- 2311.09257 UFOGen: You Forward Once Large Scale Text-to-Image Generation via Diff
        23662, -- 2311.13384 LucidDreamer: Domain-free Generation of 3D Gaussian Splatting Scenes
        23741, -- 2311.14768 AdaDiff: Adaptive Step Selection for Fast Diffusion Models
        23799, -- 2311.15744 One More Step: A Versatile Plug-and-Play Module for Rectifying Diffusi
        23869, -- 2311.16567 MobileDiffusion: Instant Text-to-Image Generation on Mobile Devices
        23873, -- 2311.16711 LEDITS++: Limitless Image Editing using Text-to-Image Models
        23916, -- 2311.17086 PEA-Diffusion: Parameter-Efficient Adapter with Knowledge Distillation
        24007, -- 2311.18158 HiPA: Enabling One-Step Text-to-Image Diffusion Models via High-Freque
        24059, -- 2311.18828 One-step Diffusion with Distribution Matching Distillation
        24224, -- 2312.02087 VideoSwap: Customized Video Subject Swapping with Interactive Semantic
        24338, -- 2312.03209 Cache Me if You Can: Accelerating Diffusion Models through Block Cachi
        24474, -- 2312.04655 ECLIPSE: A Resource-Efficient Text-to-Image Prior for Image Generation
        24498, -- 2312.04965 Inversion-Free Image Editing with Natural Language
        24515, -- 2312.05239 SwiftBrush: One-Step Text-to-Image Diffusion Model with Variational Sc
        24638, -- 2312.06738 InstructAny2Pix: Flexible Visual Editing via Multimodal Instruction Fo
        24675, -- 2312.07360 Boosting Latent Diffusion with Flow Matching
        24771, -- 2312.08873 Diffusion Cocktail: Mixing Domain-Specific Diffusion Models for Divers
        24800, -- 2312.09168 DiffusionLight: Light Probes for Free by Painting a Chrome Ball
        24837, -- 2312.09608 Faster Diffusion: Rethinking the Role of the Encoder for Diffusion Mod
        24905, -- 2312.10835 Your Student is Better Than Expected: Adaptive Teacher-Student Collabo
        25012, -- 2312.12491 StreamDiffusion: A Pipeline-level Solution for Real-time Interactive G
        25442, -- 2401.01808 aMUSEd: An Open MUSE Reproduction
        25507, -- 2401.02677 Progressive Knowledge Distillation Of Stable Diffusion XL Using Layer
        25621, -- 2401.04585 EDA-DM: Enhanced Distribution Alignment for Post-Training Quantization
        26139, -- 2401.12179 DITTO: Diffusion Inference-Time T-Optimization for Music Generation
        26333, -- 2401.14688 Taiyi-Diffusion-XL: Advancing Bilingual Text-to-Image Generation with
        27723, -- 2402.13573 ToDo: Token Downsampling for Efficient Generation of High-Resolution I
        27751, -- 2402.13929 SDXL-Lightning: Progressive Adversarial Diffusion Distillation
        27774, -- 2402.14167 T-Stitch: Accelerating Sampling in Pre-Trained Diffusion Models with T
        28067, -- 2402.17525 Diffusion Model-Based Image Editing: A Survey
        28124, -- 2402.18116 Block and Detail: Scaffolding Sketch-to-Image Generation
        28217, -- 2402.19481 DistriFusion: Distributed Parallel Inference for High-Resolution Diffu
        28326, -- 2403.01505 SCott: Accelerating Diffusion Models with Stochastic Consistency Disti
        28568, -- 2403.05121 CogView3: Finer and Faster Text-to-Image Generation via Relay Diffusio
        28625, -- 2403.06135 MACE: Mass Concept Erasure in Diffusion Models
        28961, -- 2403.10911 Efficient Diffusion-Driven Corruption Editor for Test-Time Adaptation
        29058, -- 2403.12013 GeoWizard: Unleashing the Diffusion Priors for 3D Geometry Estimation
        29060, -- 2403.12015 Fast High-Resolution Image Synthesis with Latent Adversarial Diffusion
        29072, -- 2403.12036 One-Step Image Translation with Text-to-Image Models
        29105, -- 2403.12585 LASPA: Latent Spatial Alignment for Fast Training-free Single Image Ed
        29113, -- 2403.12706 AnimateDiff-Lightning: Cross-Model Diffusion Distillation
        29132, -- 2403.12931 You Only Sample Once: Taming One-Step Text-to-Image Synthesis by Self-
        29275, -- 2403.14602 ReNoise: Real Image Inversion Through Iterative Noising
        29313, -- 2403.15048 Make VLM Recognize Visual Hallucination on Cartoon Character Image wit
        29376, -- 2403.15931 X-Portrait: Expressive Portrait Animation with Hierarchical Motion Att
        29417, -- 2403.16627 SDXS: Real-Time One-Step Latent Diffusion Models with Image Conditions
        29501, -- 2403.17919 LISA: Layerwise Importance Sampling for Memory-Efficient Large Languag
        29507, -- 2403.17933 SLEDGE: Synthesizing Driving Environments with Generative Models and R
        29746, -- 2404.00879 Model-Agnostic Human Preference Inversion in Diffusion Models
        29773, -- 2404.01197 Getting it Right: Improving Spatial Consistency in Text-to-Image Model
        29801, -- 2404.01367 Bigger is not Always Better: Scaling Properties of Latent Diffusion Mo
        29824, -- 2404.01709 Upsample Guidance: Scale Up Diffusion Models without Training
        29864, -- 2404.02241 Linear Combination of Saved Checkpoints Makes Consistency and Diffusio
        29888, -- 2404.02747 Faster Diffusion via Temporal Attention Decomposition
        29989, -- 2404.04057 Score identity Distillation: Exponentially Fast Distillation of Pretra
        30030, -- 2404.04650 InitNO: Boosting Text-to-Image Diffusion Models via Initial Noise Opti
        30539, -- 2404.12382 Lazy Diffusion Transformer for Interactive Image Editing
        30607, -- 2404.13358 Music Consistency Models
        30611, -- 2404.13491 Accelerating the Generation of Molecular Conformations with Progressiv
        30623, -- 2404.13686 Hyper-SD: Trajectory Segmented Consistency Model for Efficient Image S
        30631, -- 2404.13903 Accelerating Image Generation with Sub-path Linear Approximation Model
        30669, -- 2404.14507 Align Your Steps: Optimizing Sampling Schedules in Diffusion Models
        30746, -- 2404.16022 PuLID: Pure and Lightning ID Customization via Contrastive Alignment
        30784, -- 2404.16767 REBEL: Reinforcement Learning via Regressing Relative Rewards
        30930, -- 2404.19525 MicroDreamer: Efficient 3D Generation in $\sim$20 Seconds by Score-bas
        31023, -- 2405.01536 Customizing Text-to-Image Models with a Single Image Pair
        31089, -- 2405.03520 Is Sora a World Simulator? A Comprehensive Survey on General World Mod
        31146, -- 2405.05224 Imagine Flash: Accelerating Emu Diffusion Models with Backward Distill
        31149, -- 2405.05252 Attention-Driven Training-Free Efficiency Enhancement of Diffusion Mod
        31179, -- 2405.05967 Distilling Diffusion Models into Conditional GANs
        31231, -- 2405.07510 PeRFlow: Piecewise Rectified Flow as Universal Plug-and-Play Accelerat
        31297, -- 2405.08748 Hunyuan-DiT: A Powerful Multi-Resolution Diffusion Transformer with Fi
        31401, -- 2405.11252 Dreamer XL: Towards High-Resolution Text-to-3D Generation via Trajecto
        31525, -- 2405.13637 Curriculum Direct Preference Optimization for Diffusion and Consistenc
        31635, -- 2405.14867 Improved Distribution Matching Distillation for Fast Image Synthesis
        31637, -- 2405.14869 PuzzleAvatar: Assembling 3D Avatars from Personal Albums
        31719, -- 2405.15757 Looking Backward: Streaming Video-to-Video Translation with Feature Ba
        31806, -- 2405.16852 EM Distillation for One-step Diffusion Models
        31823, -- 2405.17082 Ensembling Diffusion Models via Adaptive Feature Aggregation
        31843, -- 2405.17398 Vista: A Generalizable Driving World Model with High Fidelity and Vers
        31859, -- 2405.17532 ClassDiffusion: More Aligned Personalization Tuning with Explicit Clas
        31973, -- 2405.18750 T2V-Turbo: Breaking the Quality Bottleneck of Video Consistency Model
        32039, -- 2405.19726 Streaming Video Diffusion: Online Video Editing with Diffusion Models
        32085, -- 2405.20289 DITTO-2: Distilled Diffusion Inference-Time T-Optimization for Music G
        32092, -- 2405.20324 Don't drop your samples! Coherence-aware training benefits Conditional
        32093, -- 2405.20327 GECO: Generative Image-to-3D within a SECOnd
        32108, -- 2405.20494 Slight Corruption in Pre-training Data Makes Better Diffusion Models
        32185, -- 2406.00505 Improving Text Generation on Images with Synthetic Captions
        32209, -- 2406.00985 ParallelEdits: Efficient Multi-object Image Editing
        32217, -- 2406.01125 $Δ$-DiT: A Training-Free Acceleration Method Tailored for Diffusion Tr
        32295, -- 2406.02347 Flash Diffusion: Accelerating Any Conditional Diffusion Model for Few
        32302, -- 2406.02430 Seed-TTS: A Family of High-Quality Versatile Speech Generation Models
        32307, -- 2406.02511 V-Express: Conditional Dropout for Progressive Training of Portrait Vi
        32397, -- 2406.03728 Evaluating Durability: Benchmark Insights into Multimodal Watermarking
        32454, -- 2406.04324 SF-V: Single Forward Video Generation Model
        32476, -- 2406.04485 GenAI Arena: An Open Evaluation Platform for Generative Models
        32669, -- 2406.06890 Motion Consistency Model: Accelerating Video Diffusion with Disentangl
        32671, -- 2406.06911 AsyncDiff: Parallelizing Diffusion Models by Asynchronous Denoising
        32737, -- 2406.07546 Commonsense-T2I Challenge: Can Text-to-Image Generation Models Underst
        32776, -- 2406.08070 CFG++: Manifold-constrained Classifier Free Guidance for Diffusion Mod
        32927, -- 2406.09750 ControlVAR: Exploring Controllable Visual Autoregressive Modeling
        33020, -- 2406.10797 STAR: Scale-wise Text-to-image generation via Auto-Regressive represen
        33149, -- 2406.11740 Imagination Policy: Using Generative Point Cloud Models for Learning M
        33231, -- 2406.12303 Immiscible Diffusion: Accelerating Diffusion Training with Noise Assig
        33265, -- 2406.12671 GeoBench: Benchmarking and Analyzing Monocular Geometry Estimation Mod
        33413, -- 2406.14539 Invertible Consistency Distillation for Text-Guided Image Editing in A
        34376, -- 2407.06937 HumanRefiner: Benchmarking Abnormal Human Generation and Refining with
        34397, -- 2407.07111 Diffusion Model-Based Video Editing: A Survey
        34462, -- 2407.08136 EchoMimic: Lifelike Audio-Driven Portrait Animations through Editable
        34510, -- 2407.08701 Live2Diff: Live Stream Translation via Uni-directional Attention in Vi
        34835, -- 2407.12718 SlimFlow: Training Smaller One-Step Diffusion Models with Rectified Fl
        34915, -- 2407.13584 Connecting Consistency Distillation to Score Distillation for Text-to-
        35193, -- 2407.17952 BetterDepth: Plug-and-Play Diffusion Refiner for Zero-Shot Monocular D
        35448, -- 2408.00735 TurboEdit: Text-Based Image Editing Using Few-Step Diffusion Models
        35771, -- 2408.06500 Music2Latent: Consistency Autoencoders for Latent Audio Compression
        35780, -- 2408.06646 Hybrid SD: Edge-Cloud Collaborative Inference for Stable Diffusion Mod
        35877, -- 2408.08332 TurboEdit: Instant text-based image editing
        36187, -- 2408.13395 Task-Oriented Diffusion Inversion for High-Fidelity Text-based Editing
        36230, -- 2408.14176 SwiftBrush v2: Make Your One-step Diffusion Model Better Than Its Teac
        36243, -- 2408.14468 K-Sort Arena: Efficient and Reliable Benchmarking for Generative Model
        36312, -- 2408.15660 Merging and Splitting Diffusion Paths for Semantically Coherent Panora
        36338, -- 2408.15991 Distribution Backtracking Builds A Faster Convergence Trajectory for D
        36452, -- 2409.00492 Accurate Compression of Text-to-Image Diffusion Models via Vector Quan
        36501, -- 2409.01347 Target-Driven Distillation: Consistency Distillation with Target Times
        36546, -- 2409.02097 LinFusion: 1 GPU, 1 Minute, 16K Image
        36921, -- 2409.10058 StyleTTS-ZS: Efficient High-Quality Zero-Shot Text-to-Speech Synthesis
        37000, -- 2409.11355 Fine-Tuning Image-Conditional Diffusion Models is Easier than You Thin
        37066, -- 2409.12431 FlexiTex: Enhancing Texture Generation with Visual Guidance
        37210, -- 2409.14993 Multi-Modal Generative AI: Multi-modal LLM, Diffusion and Beyond
        37493, -- 2409.19681 Simple and Fast Distillation of Diffusion Models
        37677, -- 2410.01699 Accelerating Auto-regressive Text-to-Image Generation with Training-fr
        37854, -- 2410.03190 Tuning Timestep-Distilled Diffusion Model Using Pairwise Sample Optimi
        37931, -- 2410.04081 Epsilon-VAE: Denoising as Visual Decoding
        37983, -- 2410.04844 PostEdit: Posterior Sampling for Efficient Zero-Shot Image Editing
        38063, -- 2410.05677 T2V-Turbo-v2: Enhancing Video Generation Model Post-Training through D
        38091, -- 2410.06084 Diversity-Rewarded CFG Distillation
        38110, -- 2410.06244 Story-Adapter: A Training-free Iterative Framework for Long Story Visu
        38131, -- 2410.06551 InstantIR: Blind Image Restoration with Instant Generative Reference
        38178, -- 2410.07133 EvolveDirector: Approaching Advanced Text-to-Image Generation with Lar
        38202, -- 2410.07303 Rectified Diffusion: Straightness Is Not Your Need in Rectified Flow
        38282, -- 2410.08261 Meissonic: Revitalizing Masked Generative Transformers for Efficient H
        38395, -- 2410.09873 Training-Free Adaptive Diffusion with Bounded Difference Approximation
        38408, -- 2410.10105 High-Precision Dichotomous Image Segmentation via Probing Diffusion Ca
        38413, -- 2410.10166 Automated Filtering of Human Feedback Data for Aligning Text-to-Image
        38451, -- 2410.10733 Deep Compression Autoencoder for Efficient High-Resolution Diffusion M
        38453, -- 2410.10738 DrivingDojo Dataset: Advancing Interactive and Knowledge-Enriched Driv
        38501, -- 2410.11081 Simplifying, Stabilizing and Scaling Continuous-Time Consistency Model
        38592, -- 2410.12266 FlashAudio: Rectified Flows for Fast and High-Fidelity Text-to-Audio G
        38615, -- 2410.12557 One Step Diffusion via Shortcut Models
        38985, -- 2410.16794 One-Step Diffusion Distillation through Score Implicit Matching
        38989, -- 2410.16892 VistaDream: Sampling multiview consistent images for single-view scene
        39149, -- 2410.18975 Unbounded: A Generative Infinite Game of Character Life Simulation
        39176, -- 2410.19355 FasterCache: Training-Free Video Diffusion Model Acceleration with Hig
        39263, -- 2410.20898 David and Goliath: Small One-step Model Beats Large Diffusion with Sco
        39370, -- 2410.22771 FuseAnyPart: Diffusion-Driven Facial Parts Swapping via Multiple Refer
        39492, -- 2411.00322 Constant Acceleration Flow
        39619, -- 2411.02397 Adaptive Caching for Faster Video Generation with Diffusion Transforme
        39702, -- 2411.04125 Community Forensics: Using Thousands of Generators to Train Fake Image
        39764, -- 2411.05007 SVDQuant: Absorbing Outliers by Low-Rank Components for 4-Bit Diffusio
        39981, -- 2411.08954 Inconsistencies In Consistency Models: Better ODE Solving Does Not Imp
        40005, -- 2411.09502 Golden Noise for Diffusion Models: A Learning Framework
        40208, -- 2411.13383 Adversarial Diffusion Compression for Real-World Image Super-Resolutio
        40355, -- 2411.15436 ConsistentAvatar: Learning to Diffuse Fully Consistent Talking Head Av
        40452, -- 2411.16720 Importance-Based Token Merging for Efficient Image and Video Generatio
        40483, -- 2411.17041 Free$^2$Guide: Gradient-Free Path Integral Control for Enhancing Text-
        40499, -- 2411.17240 Boost 3D Reconstruction using Diffusion-based Monocular Camera Calibra
        40552, -- 2411.17787 Collaborative Decoding Makes Visual Auto-Regressive Modeling Efficient
        40586, -- 2411.18263 TSD-SR: One-Step Diffusion with Target Score Distillation for Real-Wor
        40596, -- 2411.18375 Individual Content and Motion Dynamics Preserved Pruning for Video Dif
        40733, -- 2412.00100 Steering Rectified Flow Models in the Vector Field for Controlled Imag
        40807, -- 2412.01064 FLOAT: Generative Motion Latent Flow Matching for Audio-driven Talking
        40859, -- 2412.01819 Switti: Designing Scale-Wise Transformers for Text-to-Image Synthesis
        40875, -- 2412.02030 NitroFusion: High-Fidelity Single-Step Diffusion through Dynamic Adver
        40920, -- 2412.02687 SNOOPI: Supercharged One-step Diffusion Distillation with Proper Guida
        40996, -- 2412.03568 The Matrix: Infinite-Horizon World Generation with Real-Time Moving Co
        41006, -- 2412.03632 MV-Adapter: Multi-view Consistent Image Generation Made Easy
        41051, -- 2412.04301 SwiftEdit: Lightning Fast Text-Guided Image Editing via One-Step Diffu
        41110, -- 2412.04715 Addressing Attribute Leakages in Diffusion-based Image Editing without
        41155, -- 2412.05278 Birth and Death of a Rose
        41205, -- 2412.06028 FlexDiT: Dynamic Token Density Control for Diffusion Transformer
        41340, -- 2412.07772 From Slow Bidirectional to Fast Autoregressive Video Diffusion Models
        41421, -- 2412.08871 Inference-Time Diffusion Model Distillation
        41508, -- 2412.09856 LinGen: Towards High-Resolution Minute-Length Text-to-Video Generation
        41647, -- 2412.11706 AsymRnR: Video Diffusion Transformers Acceleration with Asymmetric Red
        41717, -- 2412.12444 LazyDiT: Lazy Learning for the Acceleration of Diffusion Transformers
        41863, -- 2412.14283 PixelMan: Consistent Object Editing with Diffusion Models via Pixel Ma
        41980, -- 2412.15670 BS-LDM: Effective Bone Suppression in High-Resolution Chest X-Ray Imag
        41983, -- 2412.15689 DOLLAR: Few-Step Video Generation via Distillation and Latent Reward O
        42044, -- 2412.16906 Self-Corrected Flow Distillation for Consistent One-Step and Few-Step
        42045, -- 2412.16915 FADA: Fast Diffusion Avatar Synthesis with Mixed-Supervised Multi-CFG
        42203, -- 2412.18945 Single Trajectory Distillation for Accelerating Image and Video Style
        42375, -- 2501.00740 RORem: Training a Robust Object Remover with Human-in-the-Loop
        42843, -- 2501.08316 Diffusion Adversarial Post-Training for One-Step Video Generation
        43120, -- 2501.13094 Robust Representation Consistency Model via Contrastive Denoising
        43122, -- 2501.13107 Accelerate High-Quality Diffusion Models with Inner Loop Feedback
        43260, -- 2501.15420 Visual Generation Without Guidance
        43289, -- 2501.15891 Any2AnyTryon: Leveraging Adaptive Position Embeddings for Versatile Vi
        43371, -- 2501.17578 Music2Latent2: Audio Compression with Summary Embeddings and Autoregre
        43446, -- 2501.18898 GestureLSM: Latent Shortcut based Co-Speech Gesture Generation with Sp
        43458, -- 2501.19083 MotionPCM: Real-Time Motion Synthesis with Phased Consistency Model
        43603, -- 2502.01776 Sparse VideoGen: Accelerating Video Diffusion Transformers with Spatia
        43867, -- 2502.05415 UniCMs: A Unified Consistency Model For Efficient Multimodal Generatio
        44062, -- 2502.07856 MRS: A Fast Sampler for Mean Reverting Diffusion based on ODE and SDE
        44340, -- 2502.11515 SayAnything: Audio-Driven Lip Synchronization with Conditional Video D
        44511, -- 2502.13081 Personalized Image Generation with Deep Generative Models: A Decade Su
        45355, -- 2503.01774 Difix3D+: Improving 3D Reconstructions with Single-Step Diffusion Mode
        45418, -- 2503.02537 RectifiedHR: Enable Efficient High-Resolution Image Generation via Ene
        45648, -- 2503.05978 MagicInfinite: Generating Infinite Talking Videos with Your Words and
        45668, -- 2503.06171 ROCM: RLHF on consistency models
        45714, -- 2503.06652 Adding Additional Control to One-Step Diffusion with Joint Distributio
        45717, -- 2503.06674 Learning Few-Step Diffusion Models by Trajectory Distribution Matching
        45765, -- 2503.07154 Ideas in Inference-time Scaling can Benefit Generative Pre-training Al
        45802, -- 2503.07535 LBM: Latent Bridge Matching for Fast Image-to-Image Translation
        45821, -- 2503.07677 PLADIS: Pushing the Limits of Attention in Diffusion Models at Inferen
        45822, -- 2503.07699 RayFlow: Instance-Aware Diffusion Acceleration via Adaptive Flow Traje
        45990, -- 2503.09641 SANA-Sprint: One-Step Diffusion with Continuous-Time Consistency Disti
        46083, -- 2503.10637 Distilling Diversity and Control in Diffusion Models
        46342, -- 2503.14482 ICE-Bench: A Unified and Comprehensive Benchmark for Image Creating an
        46343, -- 2503.14483 Multi-view Reconstruction via SfM-guided Monocular Depth Estimation
        46473, -- 2503.16302 Unleashing Vecset Diffusion Model for Fast Shape Generation
        46483, -- 2503.16397 Scale-wise Distillation of Diffusion Models
        46618, -- 2503.18286 CO-SPY: Combining Semantic and Pixel Features to Detect Synthetic Imag
        46625, -- 2503.18406 Instruct-CLIP: Improving Instruction-Guided Image Editing with Automat
        46644, -- 2503.18559 AMD-Hummingbird: Towards an Efficient Text-to-Video Model
        46709, -- 2503.19462 AccVideo: Accelerating Video Diffusion Model with Synthetic Dataset
        47022, -- 2503.23573 DASH: Detection and Assessment of Systematic Hallucinations of VLMs
        47186, -- 2504.01956 VideoScene: Distilling Video Diffusion Model to Generate 3D Scenes in
        47257, -- 2504.02828 Concept Lancet: Image Editing with Compositional Representation Transp
        47635, -- 2504.09885 Separate to Collaborate: Dual-Stream Diffusion Model for Coordinated P
        47809, -- 2504.12364 DMM: Building a Versatile Image Generation Model via Distillation-Base
        47827, -- 2504.12626 Packing Input Frame Context in Next-Frame Prediction Models for Video
        48361, -- 2505.01888 Rethinking Score Distilling Sampling for 3D Editing and Generation
        48417, -- 2505.02831 No Other Representation Component Is Needed: Diffusion Transformers Ca
        48433, -- 2505.03097 Not All Parameters Matter: Masking Diffusion Models for Enhancing Gene
        48478, -- 2505.04262 Bridging Geometry-Coherent Text-to-3D Generation with Multi-View Diffu
        48722, -- 2505.09358 Marigold: Affordable Adaptation of Diffusion-Based Image Generators fo
        48849, -- 2505.11257 DRAGON: A Large-Scale Dataset of Realistic Images Generated by Diffusi
        48984, -- 2505.12674 Few-Step Diffusion via Score identity Distillation
        49754, -- 2505.19602 Memory-Efficient Visual Autoregressive Modeling with Scale-Aware KV Ca
        49900, -- 2505.20755 Uni-Instruct: One-step Diffusion Model through Unified Diffusion Diver
        49926, -- 2505.21144 FastFace: Tuning Identity Preservation in Distilled Diffusion via Guid
        49928, -- 2505.21179 Normalized Attention Guidance: Universal Negative Guidance for Diffusi
        50181, -- 2505.23907 Cora: Correspondence-aware image editing using few step diffusion
        50320, -- 2506.00523 SenseFlow: Scaling Distribution Matching for Flow-based Text-to-Image
        50440, -- 2506.02294 Improving Knowledge Distillation Under Unknown Covariate Shift Through
        50491, -- 2506.03123 Dual-Expert Consistency Model for Efficient and High-Quality Video Gen
        50547, -- 2506.03988 RAID: A Dataset for Testing the Adversarial Robustness of AI-Generated
        50644, -- 2506.05301 SeedVR2: One-Step Video Restoration via Diffusion Adversarial Post-Tra
        50664, -- 2506.05350 Contrastive Flow Matching
        50904, -- 2506.09045 MagCache: Fast Video Generation with Magnitude-Aware Cache
        51224, -- 2506.14603 Align Your Flow: Scaling Continuous-Time Flow Map Distillation
        51235, -- 2506.14753 Cost-Aware Routing for Efficient Text-To-Image Generation
        51272, -- 2506.15682 Evolutionary Caching to Accelerate Your Off-the-Shelf Diffusion Model
        51317, -- 2506.17201 Hunyuan-GameCraft: High-dynamic Interactive Game Video Generation with
        51406, -- 2506.19103 Inverse-and-Edit: Effective and Fast Image Editing by Cycle Consistenc
        51586, -- 2506.23858 VMoBA: Mixture-of-Block Attention for Video Diffusion Models
        51686, -- 2507.03738 Flow-Anchored Consistency Models
        51687, -- 2507.03745 StreamDiT: Real-Time Streaming Text-to-Video Generation
        51890, -- 2507.11061 Robust 3D-Masked Part-level Editing in 3D Gaussian Splatting with Regu
        51975, -- 2507.13984 CSD-VAR: Content-Style Decomposition in Visual Autoregressive Models
        52354, -- 2508.09968 Noise Hypernetworks: Amortizing Test-Time Compute in Diffusion Models
        52654, -- 2509.04394 Transition Models: Rethinking the Generative Learning Objective
        52779, -- 2509.12203 LazyDrag: Enabling Stable Drag-Based Editing on Multi-Modal Diffusion
        53059, -- 2509.26488 dParallel: Learnable Parallel Decoding for dLLMs
        53384, -- 2510.08431 Large Scale Diffusion Distillation via Score-Regularized Continuous-Ti
        53449, -- 2510.07656 MONKEY: Masking ON KEY-Value Activation Adapter for Personalization
        53549, -- 2510.13678 FlashWorld: High-quality 3D Scene Generation within Seconds
        53597, -- 2510.14847 ImagerySearch: Adaptive Test-Time Search for Video Generation Beyond S
        53862, -- 2510.20512 EchoDistill: Bidirectional Concept Distillation for One-Step Diffusion
        53936, -- 2510.25590 RegionE: Adaptive Region-Aware Generation for Efficient Image Editing
        53969, -- 2510.25897 MIRO: MultI-Reward cOnditioned pretraining improves T2I quality and ef
        53993, -- 2510.27684 Phased DMD: Few-step Distribution Matching Distillation via Score Matc
        54309, -- 2511.17074 Diversity Has Always Been There in Your Visual Autoregressive Models
        54321, -- 2511.19365 DeCo: Frequency-Decoupled Pixel Diffusion for End-to-End Image Generat
        54419, -- 2511.22475 Adversarial Flow Models
        54433, -- 2511.19990 OmniRefiner: Reinforcement-Guided Local Diffusion Refinement
        54453, -- 2511.20549 Flash-DMD: Towards High-Fidelity Few-Step Image Generation with Effici
        54511, -- 2512.03046 MagicQuillV2: Precise and Interactive Image Editing with Layered Visua
        54600, -- 2512.05150 TwinFlow: Realizing One-step Generation on Large Models with Self-adve
        54735, -- 2512.11253 PersonaLive! Expressive Portrait Image Animation for Live Streaming
        54767, -- 2512.13592 Image Diffusion Preview with Consistency Solver
        54774, -- 2512.13006 Few-Step Distillation for Text-to-Image Generation: A Practical Guide
        54971, -- 2512.21338 HiStream: Efficient High-Resolution Video Generation via Redundancy-El
        55009, -- 2512.23709 Stream-DiffVSR: Low-Latency Streamable Video Super-Resolution via Auto
        55032, -- 2512.22374 Self-Evaluation Unlocks Any-Step Text-to-Image Generation
        55549, -- 2601.20540 Advancing Open-source World Models
        55671, -- 2602.02214 Causal Forcing: Autoregressive Diffusion Distillation Done Right for H
        56138, -- 2602.15031 EditCtrl: Disentangled Local and Global Control for Real-Time Generati
        56312, -- 2602.18993 SeaCache: Spectral-Evolution-Aware Cache for Accelerating Diffusion Mo
        56338, -- 2602.21760 Accelerating Diffusion via Hybrid Data-Pipeline Parallelism Based on C
        56360, -- 2602.24289 Mode Seeking meets Mean Seeking for Fast Long Video Generation
        56369, -- 2602.24208 SenCache: Accelerating Diffusion Model Inference via Sensitivity-Aware
        56462, -- 2603.04379 Helios: Real Real-Time Long Video Generation Model
        56583, -- 2603.07799 MWM: Mobile World Models for Action-Conditioned Consistent Prediction
        56692, -- 2603.08258 WaDi: Weight Direction-aware Distillation for One-step Image Synthesis
        56698, -- 2603.11647 OmniForcing: Unleashing Real-time Joint Audio-Visual Generation
        56756, -- 2603.12146 FlashMotion: Few-Step Controllable Video Generation with Trajectory Gu
        56944, -- 2603.21786 The Universal Normal Embedding
        57082, -- 2603.28713 DreamLite: A Lightweight On-Device Unified Model for Image Generation
        57083, -- 2603.28489 Video Generation Models as World Models: Efficient Paradigms, Architec
        57230, -- 2604.03118 Salt: Self-Consistent Distribution Matching with Cache-Aware Training
        57306, -- 2604.07209 INSPATIO-WORLD: A Real-Time 4D World Simulator via Spatiotemporal Auto
        57460, -- 2604.12322 Self-Adversarial One Step Generation via Condition Shifting
        57577, -- 2604.18168 Extending One-Step Image Generation from Class Labels to Text via Disc
        58551, -- 2604.03448 ExpressEdit: Fast Editing of Stylized Facial Expressions with Diffusio
        58966, -- 2603.23463 InverFill: One-Step Inversion for Enhanced Few-Step Diffusion Inpainti
        59034, -- 2603.22271 DUO-VSR: Dual-Stream Distillation for One-Step Video Super-Resolution
        59036, -- 2603.22125 DA-VAE: Plug-in Latent Compression for Diffusion via Detail Alignment
        59113, -- 2603.19939 Timestep-Aware Block Masking for Efficient Diffusion Model Inference
        59918, -- 2603.03657 InEdit-Bench: Benchmarking Intermediate Logical Pathways for Intellige
        60422, -- 2602.19083 ChordEdit: One-Step Low-Energy Transport for Image Editing
        60871, -- 2602.10717 Say, Dream, and Act: Learning Video World Models for Instruction-Drive
        61171, -- 2602.05449 DisCa: Accelerating Video Diffusion Transformers with Distillation-Com
        61229, -- 2602.17682 Duality Models: An Embarrassingly Simple One-step Generation Paradigm
        61386, -- 2602.03208 Spectral Evolution Search: Efficient Inference-Time Scaling for Reward
        63311, -- 2512.22288 Co-GRPO: Co-Optimized Group Relative Policy Optimization for Masked Di
        63430, -- 2512.19479 Emotion-Director: Bridging Affective Shortcut in Emotion-Oriented Imag
        63600, -- 2512.15657 SoFlow: Solution Flow Models for One-Step Generative Modeling
        64171, -- 2512.11831 On the Design of One-step Diffusion via Shortcutting Flow Paths
        64467, -- 2511.21475 MobileI2V: Fast and High-Resolution Image-to-Video on Mobile Devices
        64539, -- 2511.20307 TReFT: Taming Rectified Flow Models For One-Step Image Translation
        64688, -- 2511.18281 Uni-DAD: Unified Distillation and Adaptation of Diffusion Models for F
        64906, -- 2511.13649 Distribution Matching Distillation Meets Reinforcement Learning
        65645, -- 2511.00090 LeMiCa: Lexicographic Minimax Path Caching for Efficient Diffusion-Bas
        65925, -- 2510.21167 Blockwise Flow Matching: Improving Flow Matching Models For Efficient
        66384, -- 2510.17858 Shortcutting Pre-trained Flow Matching Diffusion Models is Almost Free
        66660, -- 2510.09094 Dense2MoE: Restructuring Diffusion Transformer to MoE for Efficient Te
        66891, -- 2510.05715 AgeBooth: Controllable Facial Aging and Rejuvenation via Diffusion Mod
        66929, -- 2510.04961 SSDD: Single-Step Diffusion Decoder for Efficient Image Tokenization
        67171, -- 2510.01339 LVTINO: LAtent Video consisTency INverse sOlver for High Definition Vi
        67319, -- 2509.26096 EVODiff: Entropy-aware Variance Optimized Diffusion Inference
        67395, -- 2509.25180 DC-Gen: Post-Training Diffusion Acceleration with Deeply Compressed La
        67406, -- 2509.25127 Score Distillation of Flow Matching Models
        67417, -- 2509.25035 Ultra-Fast Language Generation via Discrete Diffusion Divergence Instr
        68120, -- 2509.16141 AcT2I: Evaluating and Improving Action Depiction in Text-to-Image Mode
        68683, -- 2509.05441 Missing Fine Details in Images: Last Seen in High Frequencies
        69137, -- 2508.19204 LSD-3D: Large-Scale 3D Driving Scene Generation with Geometry Groundin
        69389, -- 2508.15169 MeSS: City Mesh-Guided Outdoor Scene Generation with Cross-View Consis
        69676, -- 2508.10498 TweezeEdit: Consistent and Efficient Image Editing with Path Regulariz
        70863, -- 2507.16884 SplitMeanFlow: Interval Splitting Consistency in Few-Step Generative M
        70945, -- 2507.15216 Improving Joint Embedding Predictive Architecture with Diffusion Noise
        70971, -- 2507.14797 Distilling Parallel Gradients for Fast ODE Solvers of Diffusion Models
        71093, -- 2507.11851 Your LLM Knows the Future: Uncovering Its Multi-Token Prediction Poten
        71216, -- 2507.09168 Stable Score Distillation
        71288, -- 2507.07317 ADIEE: Automatic Dataset Creation and Scorer for Instruction-Guided Im
        71479, -- 2507.03054 LATTE: Latent Trajectory Embedding for Diffusion-Generated Image Detec
        71753, -- 2506.19348 Training-Free Motion Customization for Distilled Video Generators with
        72214, -- 2506.05806 LLIA -- Enabling Low-Latency Interactive Avatars: Real-Time Audio-Driv
        72320, -- 2506.03067 EDITOR: Effective and Interpretable Prompt Inversion for Text-to-Image
        72700, -- 2505.20107 Refining Few-Step Text-to-Multiview Diffusion via Reinforcement Learni
        72704, -- 2505.19931 Accelerating Flow-Matching-Based Text-to-Speech via Empirically Pruned
        72756, -- 2505.18825 How to build a consistency model: Learning flow maps via self-distilla
        73244, -- 2504.21307 The Dual Power of Interpretable Token Embeddings: Jailbreaking Attacks
        73602, -- 2504.06897 MedSegFactory: Text-Guided Generation of Medical Image-Mask Pairs
        73870, -- 2503.19731 PCM : Picard Consistency Model for Fast Parallel Sampling of Diffusion
        74164, -- 2503.08253 SARA: Structural and Adversarial Representation Alignment for Training
        74273, -- 2503.04050 Underlying Semantic Diffusion for Effective and Efficient In-Context L
        74347, -- 2503.01323 CacheQuant: Comprehensively Accelerated Diffusion Models
        74955, -- 2502.06805 Efficient Diffusion Models: A Survey
        75528, -- 2412.07909 Explaining and Mitigating the Modality Gap in Contrastive Multimodal L
        75781, -- 2411.11727 Aligning Few-Step Diffusion Models with Dense Reward Difference Learni
        76467, -- 2409.02374 Exploring Low-Dimensional Subspaces in Diffusion Models for Controllab
        77308, -- 2405.04675 TexControl: Sketch-Based Two-Stage Fashion Image Generation Using Diff
        78148, -- 2312.03517 FRDiff : Feature Reuse for Universal Training-free Acceleration of Dif
        82847, -- 2605.05204 D-OPSD: On-Policy Self-Distillation for Continuously Tuning Step-Disti
        82874, -- 2605.06376 Continuous-Time Distribution Matching for Few-Step Diffusion Distillat
        82925, -- 2605.08078 Normalizing Trajectory Models
        83182, -- 2605.15055 DiffusionOPD: A Unified Perspective of On-Policy Distillation in Diffu
        83189, -- 2605.15190 RAVEN: Real-time Autoregressive Video Extrapolation with Consistency-m
        83209, -- 2605.14876 Unlocking Complex Visual Generation via Closed-Loop Verified Reasoning
        83684, -- 2605.21573 Lens: Rethinking Training Efficiency for Foundational Text-to-Image Mo
        83773, -- 2605.26108 Reinforcing Few-step Generators via Reward-Tilted Distribution Matchin
        83917, -- 2605.25378 CollectionLoRA: Collecting 50 Effects in 1 LoRA via Multi-Teacher On-P
        84225, -- 2511.18834 FlowSteer: Guiding Few-Step Image Synthesis with Authentic Trajectorie
        84230, -- 2511.19065 Understanding, Accelerating, and Improving MeanFlow Training
        84426, -- 2512.19048 WaTeRFlow: Watermark Temporal Robustness via Flow Consistency
        84497, -- 2601.22275 VMonarch: Efficient Video Diffusion Transformers with Structured Atten
        84514, -- 2602.12640 ImageRAGTurbo: Towards One-step Text-to-Image Generation with Retrieva
        84627, -- 2602.22654 Denoising as Path Planning: Training-Free Acceleration of Diffusion Mo
        84751, -- 2603.04870 Diffusion-Based sRGB Real Noise Generation via Prompt-Driven Noise Rep
        84838, -- 2603.10354 StyleGallery: Training-free and Semantic-aware Personalized Style Tran
        85017, -- 2603.21002 SURF: Signature-Retained Fast Video Generation
        85037, -- 2603.21864 Adaptive Video Distillation: Mitigating Oversaturation and Temporal Co
        85178, -- 2603.27599 You Only Erase Once: Erasing Anything without Bringing Unexpected Cont
        85409, -- 2604.17736 IncreFA: Breaking the Static Wall of Generative Model Attribution
        85422, -- 2604.19129 PortraitDirector: A Hierarchical Disentanglement Framework for Control
        85686, -- 2605.23458 One-Forcing: Towards Stable One-Step Autoregressive Video Generation
        85748, -- 2505.13358 One-Step Offline Distillation of Diffusion-based Models via Koopman Mo
        85825, -- 2503.02918 Straight-Line Diffusion Model for Efficient 3D Molecular Generation
        86659, -- 2510.15783 ReCon: Region-Controllable Data Augmentation with Rectification and Al
        86804, -- 2510.04153 ObCLIP: Oblivious CLoud-Device Hybrid Image Generation with Privacy Pr
        87253, -- 2506.08822 FreqPolicy: Efficient Flow-based Visuomotor Policy via Frequency Consi
        87567, -- 2507.18569 Adversarial Distribution Matching for Diffusion Distillation Towards E
        87606, -- 2507.10218 Straighten Viscous Rectified Flow via Noise Optimization
        87644, -- 2508.06160 Fewer Denoising Steps or Cheaper Per-Step Inference: Towards Compute-O
        87782, -- 2503.09675 Accelerating Diffusion Sampling via Exploiting Local Transition Cohere
        87903, -- 2411.13787 Adaptive Routing of Text-to-Image Generation Requests Between Large Cl
        88152, -- 2507.05256 SegmentDreamer: Towards High-fidelity Text-to-3D Synthesis with Segmen
        88153, -- 2507.04961 InterGSEdit: Interactive 3D Gaussian Splatting Editing with 3D Geometr
        88184, -- 2508.06033 InstantEdit: Text-Guided Few-Step Image Editing with Piecewise Rectifi
        88194, -- 2508.00697 On-Device Diffusion Transformer Policy for Efficient Robot Manipulatio
        88253, -- 2508.16212 OmniCache: A Trajectory-Oriented Global Perspective on Training-Free C
        88446, -- 2506.01955 Dual-Process Image Generation
        88485, -- 2508.21032 Reusing Computation in Text-to-Image Diffusion for Efficient Generatio
        88752, -- 2505.03194 Convergence of Consistency Model with Multistep Sampling under General
        89221, -- 2411.06503 Diffusion Sampling Correction via Approximately 10 Parameters
        90427, -- 2503.11143 GaussianIP: Identity-Preserving Realistic 3D Human Generation via Huma
        90449, -- 2408.17064 Instant Adversarial Purification with Adversarial Consistency Distilla
        90574, -- 2505.24023 Multi-Group Proportional Representations for Text-to-Image Models
        90597, -- 2504.14335 Visual Prompting for One-shot Controllable Video Editing without Inver
        90616, -- 2504.00996 TurboFill: Adapting Few-step Text-to-image Model for Fast Image Inpain
        90637, -- 2503.15927 BlockDance: Reuse Structurally Similar Spatio-Temporal Features to Acc
        90687, -- 2503.15975 Acc3D: Accelerating Single Image to 3D Diffusion Models via Edge Consi
        90739, -- 2412.06295 See Further When Clear: Curriculum Consistency Model
        90852, -- 2411.15247 Reward Fine-Tuning Two-Step Diffusion Models via Learning Differentiab
        90988, -- 2504.11295 Autoregressive Distillation of Diffusion Transformers
        91011, -- 2503.01167 Enhancing Vision-Language Compositional Understanding with Multimodal
        91236, -- 2405.19237 ConceptPrune: Concept Editing in Diffusion Models via Skilled Neuron P
        91308, -- 2406.14548 Consistency Models Made Easy
        91453, -- 2410.14919 Adversarial Score identity Distillation: Rapidly Surpassing the Teache
        91516, -- 2502.17099 Improved Diffusion-based Generative Model with Better Adversarial Robu
        91832, -- 2406.01561 Guided Score identity Distillation for Data-Free One-Step Text-to-Imag
        92024, -- 2410.14895 Truncated Consistency Models
        92025, -- 2502.02922 Elucidating the Preconditioning in Consistency Distillation
        92103, -- 2410.05760 Training-Free Diffusion Model Alignment with Sampling Demons
        92118, -- 2410.11835 Aligned Datasets Improve Detection of Latent Diffusion-Generated Image
        92140, -- 2410.03456 Dynamic Diffusion Transformer
        92535, -- 2606.03746 Qwen-Image-Flash: Beyond Objective Design
        93714, -- 2509.21513 DistillKac: Few-Step Image Generation via Damped Wave Equations
        93925, -- 2509.25740 Dragging with Geometry: From Pixels to Geometry-Guided Image Editing
        94309, -- 2604.03674 DiffSparse: Accelerating Diffusion Transformers with Learned Token Spa
        94588, -- 2509.22323 RAPID$^3$: Tri-Level Reinforced Acceleration Policies for Diffusion Tr
        94883, -- 2601.19961 MeanCache: From Instantaneous to Average Velocity for Accelerating Flo
        94989, -- 2603.00458 Improved Adversarial Diffusion Compression for Real-World Video Super-
        95001, -- 2604.04843 InfBaGel: Human-Object-Scene Interaction Generation with Dynamic Perce
        95056, -- 2509.22925 Soft-Di[M]O: Improving One-Step Discrete Image Generation with Soft Em
        95098, -- 2606.05254 Flash-WAM: Modality-Aware Distillation for World Action Models
        97530, -- 2603.10451 FAR-Dex: Few-Shot Data Augmentation and Adaptive Residual Policy Refin
        98038, -- 2606.09516 SwiftVR: Real-Time One-Step Generative Video Restoration
        98194, -- 2606.12072 World Model Self-Distillation: Training World Models to Solve General
        98408, -- 2606.14732 Steady-Forcing: Balancing Spatial Persistence and Motion Continuity in
        98846, -- 2606.27377 DanceOPD: On-Policy Generative Field Distillation
        99076, -- 2607.01642 Multi-Resolution Flow Matching: Training-Free Diffusion Acceleration v
        99105, -- 2606.32020 Cross-Space Distillation: Teaching One-Step Students with Modern Diffu
        99107, -- 2606.02521 Drifting Preference Optimization for One-Step Generative Models
        99118, -- 2606.10309 Dissect and Prune: Enhancing Robustness in AI-Generated Image Detectio
        99210, -- 2606.11155 Mean Flow Distillation: Robust and Stable Distillation for Flow Matchi
        99429, -- 2606.07835 Mitigating the Contractivity Trap in Diffusion ODEs via Stein Stabiliz
        99596, -- 2605.21280 Let EEG Models Learn EEG
        99814, -- 2510.09060 Letting Trajectories Spread: Quality-Preserving Control for Diverse Fl
        99852, -- 2606.26795 NaviCache: Test-Time Self-Calibration Caching for Video Generation
        100967, -- 2506.22304 Unfolding Generative Flows with Koopman Operators: Trajectory-Preservi
        102585, -- 2607.03524 Perceptual Flow Matching for Few-Step Generative Modeling
        102623, -- 2607.06291 AlayaWorld: Long-Horizon and Playable Video World Generation
        102723, -- 2607.03803 CineMobile: On-Device Image-to-Video Diffusion for Cinematic Camera Mo
        104043, -- 2607.15273 MeanFlowNFT: Bringing Forward-Process RL to Average-Velocity Generator
        104392, -- 2607.17972 DiFA: Inference-Time Forward-Process Alignment for Diffusion Models
        104585, -- 2607.24731 Rethinking Classifier-Free Guidance in On-Policy Diffusion Distillatio
        105847, -- 2607.26004 Parallel Decoding Distillation for Fast Image and Video Generation
        105983, -- 2605.28657 DEMON: Diffusion Engine for Musical Orchestrated Noise
        106425, -- 2508.06082 SwiftVideo: A Unified Framework for Few-Step Video Generation Through
        106833, -- 2601.10373 Towards Efficient Low-rate Image Compression with Frequency-aware Diff
        106929, -- 2509.00036 A-FloPS: Accelerating Diffusion Models via Adaptive Flow Path Sampler
        107009, -- 2511.08987 WDT-MD: Wavelet Diffusion Transformers for Microaneurysm Detection in
        107063, -- 2511.11688 Hierarchical Schedule Optimization for Fast and Robust Diffusion Model
        107398, -- 2511.16047 AMS-KV: Adaptive KV Caching in Multi-Scale Visual Autoregressive Trans
        107658, -- 2508.21019 Phased One-Step Adversarial Equilibrium for Video Diffusion Models
        108644, -- 2608.02602 AURORA-LM: Autoencoding Unified Representation for Continuous-Latent D
        108650, -- 2608.03316 Any-OPD: Heterogeneous On-Policy Distillation for Flow-Matching Models
        108730, -- 2608.04349 Poly-OPD: Heterogeneous Multi-Teacher On-Policy Distillation for Capab
        109129, -- 2608.13546 Alaya-EVOKE: From Linear-Scaling Supervision to Endless World
        112274, -- 2509.18699 AGSwap: Overcoming Category Boundaries in Object Fusion via Adaptive G
        112436, -- 2408.14738 Learning Differentially Private Diffusion Models via Stochastic Advers
        112587, -- 2407.10373 Mutual Learning for Acoustic Matching and Dereverberation via Visual S
        113029, -- 2407.12676 CoSIGN: Few-Step Guidance of ConSIstency Model to Solve General INvers
        113188, -- 2311.06322 Post-training Quantization with Progressive Calibration and Activation
        113932, -- 2609.03563 FlashRender: Few-Step Generative Rendering via Camera-Controlled Video
        114018, -- 2609.05588 GE-Act 2.0: Pretraining and Scaling a World-Action Model for Robotic M
        115842, -- 2403.02981 Doubly Abductive Counterfactual Inference for Text-based Image Editing
        116045, -- 2406.05478 Revisiting Non-Autoregressive Transformers for Efficient Image Synthes
        116117, -- 2404.11120 TiNO-Edit: Timestep and Noise Optimization for Robust Diffusion-Based
        116530, -- 2404.01862 Co-Speech Gesture Video Generation via Motion-Decoupled Diffusion Mode
        116608, -- 2404.05661 Automatic Controllable Colorization via Imagination
        117716, -- 2511.19778 Phase-Aligned RoPE for Mixed-Resolution Diffusion Transformer
        117898, -- 2603.06275 Spectral and Trajectory Regularization for Diffusion Transformer Super
        118374, -- 2607.03960 Reward Lightning: Fast Video Generation via Homologous Preference Dist
        118405, -- 2607.19895 OSVE: One Step Video Editing with One Step Diffusion Models
        118413, -- 2607.14976 From Draft to Draft-Free: One-Step Video Object Removal via Privileged
        118430, -- 2601.02211 TexTailor: Inference-Time Textual Guidance Tailoring for Multimodal Di
        118445, -- 2607.22231 TRaM-VSR: Importance-Aware Token Routing and Merging for One-Step Diff
        118446, -- 2606.28094 OSOR: One-Step Diffusion Inpainting for Effect-Aware Object Removal
        118452, -- 2607.00987 AVSR-Diff: Scale-Agnostic Diffusion Priors for Temporally Consistent A
        118468, -- 2603.20828 EruDiff: Refactoring Knowledge in Diffusion Models for Advanced Text-t
        118531, -- 2602.10764 Dual-End Consistency Model
        118543, -- 2605.22011 Rethinking Token Reduction for Diffusion Models via Output-Similarity-
        118544, -- 2510.05509 Be Tangential to Manifold: Discovering Riemannian Metric for Diffusion
        118552, -- 2607.09753 Unified Backbone Refinement for Diffusion Models via Internal-Latent A
        118560, -- 2606.22394 Curvature-Adaptive Consistency Flow Matching: Autonomous Trajectory Op
        118620, -- 2604.19238 Allo{SR}2: Rectifying One-Step Super-Resolution to Stay Real via Allom
        119282, -- 2607.09193 YeTI: You Only Need Two Noisy Images for Real-World sRGB Noise Generat
        119430, -- 2604.13509 DiT as Real-Time Rerenderer: Streaming Video Stylization with Autoregr
        120755, -- 2605.23381 VDE: Training-Free Accelerating Rectified Flow Model via Velocity Deco
        121456, -- 2604.05761 Improving Controllable Generation: Faster Training and Better Performa
        122022, -- 2609.20744 Video DeltaNet: A Video-Native Hybrid Attention for Livestream Video G
        122120, -- 2609.24788 Streaming Video Editing with Easy Adaptation
        122290, -- 2609.33748 AnyStep-WAM: Budget-Aligned Distillation and Adaptive Inference for Wo
        122549, -- 2609.30840 Aligning One-Step Generative Models with Reward-Weighted Transport Dis
        122911, -- 2609.36995 Salt++: Context-Aligned Post-Training for Few-Step Streaming Multimoda
        123053, -- 2610.13944 InstantFusion: A Shared Latent Interface for Heterogeneous Image Gener
        123123, -- 2610.12102 Few-Step Generation via Data-Space Iteration
        123727, -- 2610.09221 Consistent Distribution Matching for Data-Free Diffusion Distillation
        123757, -- 2610.25404 MT Forcing: Towards Stable and Consistent Multi-Turn Image Editing wit
        125006, -- 2610.10859 Enabling Preference-driven Unlearning in Few-step Distilled Text-to-Im
        125233, -- 2605.07907 Consistency Regularised Gradient Flows for Inverse Problems
        125516, -- 2605.09503 PermuQuant: Lowering Per-Group Quantization Error by Reordering Channe
        126013, -- 2605.16789 Accelerating Rectified Flow Models via Trajectory-Aware Caching
        126275, -- 2605.18346 Focused Forcing: Content-Aware Per-Frame KV Selection for Efficient Au
        126603, -- 2605.23522 PRECISE: SDE-Consistent Stochastic Sampling for RL Post-Training of Fl
        127506, -- 2605.16649 AtlasVid: Efficient Ultra-High-Resolution Long Video Generation via De
        127943, -- 2605.27336 PARE: Pruning and Adaptive Routing for Efficient Video Generation
        128242, -- 2610.16448 Tikhonov-Stabilized Bezier Representation Forecasting for Training-fre
        128531, -- 2602.03627 Ultra Fast PDE Solving via Physics Guided Few-step Diffusion
        129051, -- 2610.22370 Which Tokens to Merge? Diffusion Dynamics for Efficient Image Generati
        129082, -- 2604.23552 On the Memorization of Consistency Distillation for Diffusion Models
        130018, -- 2606.29451 The Platonic Defense: Backdoor Defense for Self-Supervised Encoders in
        130449, -- 2607.20048 Importance-Aware OBS Pruning for Diffusion Models
        131097, -- 2606.29287 Beyond Trajectory Matching: Reflow with Marginal Distribution Alignmen
        131098, -- 2605.16732 DiRotQ: Rotation-Aware Quantization for 4-bit Diffusion Transformers
        131297, -- 2610.30129 Rethinking Video Autoencoders for Interactive World Models
        131603, -- 2610.39633 Intrinsic Distribution Matching
        131623, -- 2610.39663 AB-Attention: Accurate Block Attention for Accelerating Video Diffusio
        131882, -- 2611.03404 VidDub: Replacement-Aware Distillation for Two-Step Video Dubbing
        131898, -- 2611.05648 NitroFusion2: Bringing Adversarial Loss to the Text Stream of Multimod
        132057  -- 2604.02028 Why Gaussian Diffusion Models Fail on Discrete Data and How to Prevent
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
        1756, -- 1901.05103 DeepSDF: Learning Continuous Signed Distance Functions for Shape Repre
        3673, -- 2006.03997 MeshSDF: Differentiable Iso-Surface Extraction
        3736, -- 2006.09661 Implicit Neural Representations with Periodic Activation Functions
        6060, -- 2106.10689 NeuS: Learning Neural Implicit Surfaces by Volume Rendering for Multi-
        6085, -- 2106.12052 Volume Rendering of Neural Implicit Surfaces
        7582, -- 2112.11427 StyleSDF: High-Resolution 3D-Consistent Image and Geometry Generation
        8323, -- 2203.09692 Facial Geometric Detail Recovery via Implicit Representation
        8950, -- 2205.02836 Neural 3D Scene Reconstruction with the Manhattan-world Assumption
        9218, -- 2205.13524 PREF: Phasorial Embedding Fields for Compact Neural Representations
        9572, -- 2206.10885 KiloNeuS: A Versatile Neural Implicit Surface Representation for Real-
        9596, -- 2206.12055 SDF-StyleGAN: Implicit SDF-Based StyleGAN for 3D Shape Generation
        9842, -- 2207.09686 Object-Compositional Neural Implicit Surfaces
        10439, -- 2209.14072 City-scale Incremental Neural Mapping with Three-layer Sampling and Pa
        11513, -- 2211.12018 Level-S$^2$fM: Structure from Motion on Neural Level Set of Implicit S
        11598, -- 2211.13757 Diffusion-SDF: Conditional Generative Modeling of Signed Distance Func
        11615, -- 2211.14086 ShadowNeuS: Neural SDF Reconstruction by Shadow Ray Supervision
        11819, -- 2212.02761 Learning Neural Parametric Head Models
        11839, -- 2212.03293 Diffusion-SDF: Text-to-Shape via Voxelized Diffusion
        13783, -- 2303.08605 RICO: Regularizing the Unobservable for Indoor Compositional Reconstru
        13815, -- 2303.09152 Learning a Room with the Occ-SDF Hybrid: Signed Distance Function Ming
        13898, -- 2303.10709 NeRF-LOAM: Neural Implicit Representation for Large-Scale Incremental
        13924, -- 2303.11219 NeTO:Neural Reconstruction of Transparent Objects with Self-Occlusion
        13978, -- 2303.11963 NEMTO: Neural Environment Matting for Novel View and Relighting Synthe
        13981, -- 2303.12012 NeAT: Learning Neural Implicit Surfaces with Arbitrary Topologies from
        13996, -- 2303.12280 NLOS-NeuS: Non-line-of-sight Neural Implicit Surface
        14037, -- 2303.13022 ENVIDR: Implicit Differentiable Renderer with Neural Environment Light
        14046, -- 2303.13190 Marching-Primitives: Shape Abstraction from Signed Distance Function
        14087, -- 2303.13855 Deformable Model-Driven Neural Rendering for High-Fidelity 3D Reconstr
        14280, -- 2303.17015 HyperDiffusion: Generating Implicit Neural Fields with Weight-Space Di
        14422, -- 2304.01480 FineRecon: Depth-aware Feed-forward Network for Detailed 3D Reconstruc
        14550, -- 2304.04179 Sparse Dense Fusion for 3D Object Detection
        14655, -- 2304.06197 SURFSUP: Learning Fluid Simulation for Novel Surfaces
        14757, -- 2304.08706 Looking Through the Glass: Neural Surface Reconstruction Against High
        14929, -- 2304.12439 TextMesh: Generation of Realistic 3D Meshes From Text Prompts
        14978, -- 2304.13445 Neural-PBIR Reconstruction of Shape, Material, and Illumination
        15237, -- 2305.03043 Single-Shot Implicit Morphable Faces with Consistent Texture Parameter
        15318, -- 2305.04461 Locally Attentional SDF Diffusion for Controllable 3D Shape Generation
        15849, -- 2305.12411 Synthesizing Diverse Human Motions in 3D Indoor Scenes
        16050, -- 2305.14236 REC-MV: REconstructing 3D Dynamic Cloth from Monocular Videos
        16248, -- 2305.15399 Sin3DM: Learning a Diffusion Model from a Single 3D Textured Shape
        16849, -- 2306.01405 Learning Signed Distance Functions from Noisy 3D Point Clouds via Nois
        17547, -- 2306.10003 C2F2NeUS: Cascade Cost Frustum Fusion for High Fidelity and Generaliza
        17883, -- 2306.16928 One-2-3-45: Any Single Image to 3D Mesh in 45 Seconds without Per-Shap
        18547, -- 2307.12194 LIST: Learning Implicitly from Spatial Transformers for Single-View 3D
        19279, -- 2308.07868 ObjectSDF++: Improved Object-Compositional Neural Implicit Surfaces
        19284, -- 2308.07903 Relightable and Animatable Neural Avatar from Sparse-View Video
        19405, -- 2308.09421 MonoNeRD: NeRF-like Representations for Monocular 3D Object Detection
        19421, -- 2308.09591 O$^2$-Recon: Completing 3D Reconstruction of Occluded Objects in the S
        19727, -- 2308.12590 Self-supervised Learning of Implicit Shape Representation with Dense C
        19789, -- 2308.13404 Relighting Neural Radiance Fields with Shadow and Highlight Hints
        19868, -- 2308.14616 VoroMesh: Learning Watertight Surface Meshes with Voronoi Diagrams
        19915, -- 2308.15461 Canonical Factors for Hybrid Neural Fields
        19922, -- 2308.15536 DebSDF: Delving into the Details and Bias of Neural Indoor Scene Recon
        20159, -- 2309.03160 ResFields: Residual Neural Fields for Spatiotemporal Signals
        20306, -- 2309.05810 SHIFT3D: Synthesizing Hard Inputs For Tricking 3D Detectors
        20601, -- 2309.10336 Anti-Aliased Neural Implicit Surfaces with Encoding Level of Detail
        20949, -- 2309.15164 3D Reconstruction with Generalizable Neural Fields using Scene Priors
        20964, -- 2309.15426 NeuRBF: A Neural Fields Representation with Adaptive Radial Basis Func
        21170, -- 2310.00615 Scene-aware Human Motion Forecasting via Mutual Distance Prediction
        21219, -- 2310.01140 Neural Processing of Tri-Plane Hybrid Neural Fields
        22427, -- 2310.15168 Ghost on the Shell: An Expressive Representation of General 3D Shapes
        23611, -- 2311.12602 TouchSDF: A DeepSDF Approach for 3D Shape Reconstruction using Vision-
        23616, -- 2311.12775 SuGaR: Surface-Aligned Gaussian Splatting for Efficient 3D Mesh Recons
        23775, -- 2311.15435 Functional Diffusion
        23777, -- 2311.15439 Efficient Encoding of Graphics Primitives with Simplex-based Structure
        24077, -- 2312.00093 GraphDreamer: Compositional 3D Scene Synthesis from Scene Graphs
        24326, -- 2312.03029 HHAvatar: Gaussian Head Avatar with Dynamic Hairs
        24336, -- 2312.03160 HybridNeRF: Efficient Neural Rendering via Adaptive Volumetric Surface
        24484, -- 2312.04803 SuperNormal: Neural Surface Reconstruction via Multi-View Normal Integ
        24652, -- 2312.06947 MaTe3D: Mask-guided Text-based 3D-aware Portrait Editing
        24803, -- 2312.09222 Mosaic-SDF for 3D Generative Models
        24935, -- 2312.11461 GAvatar: Animatable 3D Gaussian Avatars with Implicit Mesh Learning
        25229, -- 2312.16218 Hyper-VolTran: Fast and Generalizable One-Shot Image to 3D Object Stru
        26390, -- 2401.15841 2L3: Lifting Imperfect Generated 2D Images into Accurate 3D
        26482, -- 2401.17053 BlockFusion: Expandable 3D Scene Generation using Latent Tri-plane Ext
        28387, -- 2403.02460 MagicClay: Sculpting Meshes With Generative Neural Fields
        28766, -- 2403.08055 DrivAerNet: A Parametric Car Dataset for Data-Driven Aerodynamic Desig
        28922, -- 2403.10357 ANIM: Accurate Neural Implicit Model for Human Reconstruction from a s
        29049, -- 2403.11899 GNeRP: Gaussian-guided Neural Reconstruction of Reflective Objects wit
        29125, -- 2403.12870 PoNQ: a Neural QEM-based Mesh Representation
        29436, -- 2403.16964 GSDF: 3DGS Meets SDF for Improved Rendering and Reconstruction
        29527, -- 2403.18241 NeuSDFusion: A Spatial-Aware Generative Model for 3D Shape Completion,
        32437, -- 2406.04254 GeoGen: Geometry-Aware Generative Modeling via Signed Distance Functio
        33209, -- 2406.12121 TutteNet: Injective 3D Deformations by Composition of 2D Mesh Deformat
        33751, -- 2406.18544 GS-ROR$^2$: Bidirectional-guided 3DGS and SDF for Reflective Object Re
        34482, -- 2407.08414 MeshAvatar: Learning High-quality Triangular Human Avatars from Multi-
        34657, -- 2407.10707 Interactive Rendering of Relightable and Animatable Gaussian Avatars
        34963, -- 2407.14257 SparseCraft: Few-Shot Neural Reconstruction through Stereopsis Guided
        35254, -- 2407.19108 ObjectCarver: Semi-automatic segmentation, reconstruction and separati
        35981, -- 2408.10198 MeshFormer: High-Quality Mesh Generation with 3D-Guided Reconstruction
        37057, -- 2409.12193 Vista3D: Unravel the 3D Darkside of a Single Image
        37534, -- 2409.20140 RISE-SDF: a Relightable Information-Shared Signed Distance Field for G
        38045, -- 2410.05530 VisDiff: SDF-Guided Polygon Generation for Visibility Reconstruction a
        38462, -- 2410.10790 Sitcom-Crafter: A Plot-Driven Human Motion Generation System in 3D Sce
        39222, -- 2410.20220 Neural Fields in Robotics: A Survey
        39937, -- 2411.08017 Wavelet Latent Diffusion (Wala): Billion-Parameter 3D Generative Model
        40153, -- 2411.12197 MTFusion: Reconstructing Any 3D Object from Single Image Using Multi-w
        40309, -- 2411.15018 Neural 4D Evolution under Large Topological Changes from 2D Images
        40473, -- 2411.16898 G2SDF: Surface Reconstruction from Explicit Gaussians with Implicit SD
        40591, -- 2411.18311 Neural Surface Priors for Editable Gaussian Splatting
        41038, -- 2412.04120 CrossSDF: 3D Reconstruction of Thin Structures From Cross-Sections
        43942, -- 2502.06608 TripoSG: High-Fidelity 3D Shape Synthesis using Large-Scale Rectified
        44485, -- 2502.12894 CAST: Component-Aligned 3D Scene Reconstruction from an RGB Image
        49189, -- 2505.14521 Sparc3D: Sparse Representation and Construction for High-Resolution 3D
        49517, -- 2505.17412 Direct3D-S2: Gigascale 3D Generation Made Easy with Spatial Sparse Att
        51028, -- 2506.10816 Occlusion-Aware 3D Hand-Object Pose Estimation with Masked AutoEncoder
        51912, -- 2507.11589 Einstein Fields: A Neural Perspective To Computational General Relativ
        52008, -- 2507.15629 Gaussian Splatting with Discretized SDF for Relightable Assets
        54667, -- 2512.07107 COREA: Coarse-to-Fine 3D Representation Alignment Between Relightable
        54681, -- 2512.04434 Predicting Time-Dependent Flow Over Complex Geometries Using Operator
        56572, -- 2603.00446 HydroShear: Hydroelastic Shear Simulation for Tactile Sim-to-Real Rein
        58763, -- 2603.28548 Seen2Scene: Completing Realistic 3D Scenes with Visibility-Guided Flow
        58895, -- 2603.25623 Accurate Surface and Reflectance Modelling from 3D Radar Data with Neu
        58911, -- 2603.24278 TopoMesh: High-Fidelity Mesh Autoencoding via Topological Unification
        62311, -- 2601.13603 DCCVT: Differentiable Clipped Centroidal Voronoi Tessellation
        63436, -- 2512.19390 TwinAligner: Visual-Dynamic Alignment Empowers Physics-aware Real2Sim2
        63982, -- 2512.07527 From Orbit to Ground: Generative City Photogrammetry from Extreme Off-
        64675, -- 2511.18387 Scaling Implicit Fields via Hypernetwork-Driven Multiscale Coordinate
        64730, -- 2511.17364 SVRecon: Sparse Voxel Rasterization for Surface Reconstruction
        64873, -- 2511.14539 Learning Compact Latent Space for Representing Neural Signed Distance
        65077, -- 2511.10040 LoG3D: Ultra-High-Resolution 3D Shape Modeling via Local-to-Global Par
        65447, -- 2511.02064 MCHex: Marching Cubes Based Adaptive Hexahedral Mesh Generation with G
        67906, -- 2509.20081 DB-TSDF: Directional Bitmask-based Truncated Signed Distance Fields fo
        68292, -- 2509.13688 CraftMesh: High-Fidelity Generative Mesh Manipulation via Poisson Seam
        68423, -- 2509.11185 SAMP: Spatial Anchor-based Motion Policy for Collision-Aware Robotic M
        68583, -- 2509.07493 Accurate and Complete Surface Reconstruction from 3D Gaussians via Dir
        70509, -- 2507.23162 Neural Multi-View Self-Calibrated Photometric Stereo without Photometr
        71384, -- 2507.04749 MatDecompSDF: High-Fidelity 3D Shape and PBR Material Decomposition fr
        71953, -- 2506.13492 GeoSDF: Plane Geometry Diagram Synthesis via Signed Distance Field
        73052, -- 2505.10824 Textured mesh Quality Assessment using Geometry and Color Field Simila
        74111, -- 2503.10170 GS-SDF: LiDAR-Augmented Gaussian Splatting and Neural SDF for Geometri
        74205, -- 2503.06677 REArtGS: Reconstructing and Generating Articulated Objects via 3D Gaus
        76295, -- 2409.16178 SDFit: 3D Object Pose and Shape by Fitting a Morphable SDF to a Single
        76618, -- 2403.05466 Grasping Trajectory Optimization with Point Clouds
        77219, -- 2405.14580 LDM: Large Tensorial SDF Model for Textured Mesh Generation
        77297, -- 2405.05872 FlockGPT: Guiding UAV Flocking with Linguistic Orchestration
        78058, -- 2312.13277 Deep Learning on Object-centric 3D Neural Fields
        78974, -- 2305.17110 IndustReal: Transferring Contact-Rich Assembly Tasks from Simulation t
        80234, -- 2201.13360 Hydra: A Real-time Spatial Perception System for 3D Scene Graph Constr
        81405, -- 2003.10432 Atlas: End-to-End 3D Scene Reconstruction from Posed Images
        82073, -- 1803.04345 Sparse 3D Topological Graphs for Micro-Aerial Vehicle Planning
        82318, -- 1611.03631 Voxblox: Incremental 3D Euclidean Signed Distance Fields for On-Board
        83989, -- 2503.09750 SASNet: Spatially-Adaptive Sinusoidal Networks for INRs
        85186, -- 2603.28064 4DSurf: High-Fidelity Dynamic Scene Surface Reconstruction
        85572, -- 2605.17014 RHINO: Reconstructing Human Interactions with Novel Objects from Monoc
        85623, -- 2104.04532 Neural RGB-D Surface Reconstruction
        87675, -- 2505.04813 WIR3D: Visually-Informed and Geometry-Aware 3D Shape Abstraction
        87697, -- 2506.23236 VolumetricSMPL: A Neural Volumetric Body Model for Efficient Interacti
        87719, -- 2505.24431 Bridging 3D Anomaly Localization and Repair via High-Quality Continuou
        87869, -- 2507.15602 SurfaceSplat: Connecting Surface Reconstruction and Gaussian Splatting
        88059, -- 2506.23854 HiNeuS: High-fidelity Neural Surface Mitigating Low-texture and Reflec
        88119, -- 2508.00558 Guiding Diffusion-Based Articulated Object Generation by Partial Point
        88416, -- 2503.22349 GCRayDiffusion: Pose-Free Surface Reconstruction via Geometric Consist
        90231, -- 2505.18932 Geometry-guided Online 3D Video Synthesis with Multi-View Temporal Con
        90250, -- 2412.16361 Toward Robust Neural Reconstruction from Sparse Point Sets
        90255, -- 2412.10084 ProbeSDF: Light Field Probes For Neural Surface Reconstruction
        90313, -- 2411.14628 HotSpot: Signed Distance Function Optimization with an Asymptotically
        90571, -- 2412.07237 ArtFormer: Controllable Generation of Diverse 3D Articulated Objects
        90592, -- 2409.02482 Volumetric Surfaces: Representing Fuzzy Geometries with Layered Meshes
        90732, -- 2503.18361 NeRFPrior: Learning Neural Radiance Field as a Prior for Indoor Scene
        90755, -- 2403.10344 ViiNeuS: Volumetric Initialization for Implicit Neural Surface Reconst
        90785, -- 2504.20026 LIRM: Large Inverse Rendering Model for Progressive Reconstruction of
        90793, -- 2503.23670 Learning Bijective Surface Parameterization for Inferring Signed Dista
        90872, -- 2502.02187 ShapeShifter: 3D Variations Using Multiscale and Sparse Point-Voxel Di
        90895, -- 2503.00881 Evolving High-Quality Rendering and Reconstruction in a Unified Framew
        90906, -- 2504.02465 RASP: Revisiting 3D Anamorphic Art for Shadow-Guided Packing of Irregu
        90911, -- 2504.08410 PMNI: Pose-free Multi-view Normal Integration for Reflective and Textu
        91893, -- 2501.14038 Implicit Neural Surface Deformation with Explicit Velocity Fields
        92059, -- 2406.12082 Uncertainty modeling for fine-tuned implicit functions
        92283, -- 2410.01202 AniSDF: Fused-Granularity Neural Surfaces with Anisotropic Encoding fo
        94400, -- 2604.03302 Beyond Static Vision: Scene Dynamic Field Unlocks Intuitive Physics Un
        95243, -- external DepthMesh: A Dual-End Complementary Online Depth Estimation and Mesh R
        95272, -- 2509.00836 One-Step Model Predictive Path Integral for Manipulator Motion Plannin
        95305, -- 2509.24661 CEDex: Cross-Embodiment Dexterous Grasp Generation at Scale from Human
        95352, -- external SplatCtrl: Perception–Action Coupling Via Gaussian Scene Representatio
        95696, -- external Approximated Collision Detection for Contact-Rich Dexterous Manipulati
        95813, -- external Amortized NeuralSDF-Mesh Collision Detection for Robotic Contact Simul
        95844, -- 2509.13534 Embracing Bulky Objects with Humanoid Robots: Whole-Body Manipulation
        95892, -- 2507.10204 REACT: Real-Time Entanglement-Aware Coverage Path Planning for Tethere
        95976, -- external Risk-Aware and Scalable Hierarchical Motion Planning for Large-Scale R
        96122, -- 2411.15468 SplatSDF: Boosting SDF-NeRF Via Architecture-Level Fusion with Gaussia
        96164, -- 2505.13667 Adaptive Diffusion Constrained Sampling for Bimanual Robot Manipulatio
        96343, -- 2509.20681 Efficient Construction of Implicit Surface Models from a Single Image
        96355, -- external Geometry-Aware Control Barrier Functions for Collision Avoidance Via B
        96557, -- 2602.12549 Eva-Tracker: ESDF-Update-Free, Visibility-Aware Planning with Target R
        96767, -- external DisFlow: Scene Flow from Distance Field for Object Pose, Velocity Trac
        97000, -- external Overcoming Explicit Environment Representations with Geometric Fabrics
        97085, -- external Implicit LiDAR SLAM with Confidence-Guided SDF and Normal-Driven Sampl
        97688, -- 2602.23926 Leveraging Geometric Prior Uncertainty and Complementary Constraints f
        98556, -- 2606.20563 JanusMesh: Fast and Zero-Shot 3D Visual Illusion Generation via Cross-
        99344, -- 2606.01649 PhyScene3D: Physically Consistent 3D Interactive Tabletop Scene Genera
        101330, -- 2605.25503 Metric—Phase Fields: Decoupling Distance and Sign for Thin-Structure R
        101419, -- 2507.13595 NoiseSDF2NoiseSDF: Learning Clean Neural Fields from Noisy Supervision
        102230, -- 2510.22491 LAMP: Data-Efficient Linear Affine Weight-Space Models for Parameter-C
        104385, -- 2607.13365 DiffGI: Differentiable Geometry Images for High-Fidelity Thin-Shell 3D
        104516, -- 2607.21485 Recurrent Sinusoidal INRs for Efficient High-Fidelity Representation
        104745, -- 2604.25936 SAND: Spatially Adaptive Network Depth for Fast Sampling of Neural Imp
        104753, -- 2605.03623 A Few-Step Generative Model on Cumulative Flow Maps
        104777, -- 2607.16946 Points as Tori: Fast Pointwise Signed Distance for Point Clouds
        104841, -- 2604.00157 Dual Contouring of Signed Distance Data
        105381, -- external Mask2Surface: Motion Correction and Super-Resolution for Cardiac Surfa
        105510, -- 2307.08716 Pairwise-Constrained Implicit Functions for 3D Human Heart Modeling
        105783, -- 2509.08991 UltrON: Ultrasound Occupancy Networks
        105807, -- 2506.00498 UNSURF: Uncertainty Quantification for Cortical Surface Reconstruction
        105821, -- 2506.16556 VesselSDF: Distance Field Priors for Vascular Network Reconstruction
        106687, -- 2512.05920 NICE: Neural Implicit Craniofacial Model for Orthognathic Surgery Pred
        106769, -- 2508.19305 Geo2Vec: Shape- and Distance-Aware Neural Representation of Geospatial
        107262, -- 2511.09944 TSPE-GS: Probabilistic Depth Extraction for Semi-Transparent Surface R
        109473, -- 2304.13614 Multi-View Stereo Representation Revisit: Region-Aware MVSNet
        112187, -- 2506.24096 MILo: Mesh-In-the-Loop Gaussian Splatting for Detailed and Efficient S
        112195, -- 2509.21007 Marching Neurons: Accurate Surface Extraction for Neural Implicit Shap
        112199, -- 2506.13050 NeuVAS: Neural Implicit Surfaces for Variational Shape Modeling
        112217, -- 2509.05345 INF-3DP: Implicit Neural Fields for Collision-Free Multi-Axis 3D Print
        112220, -- 2506.07020 CrossGen: Learning and Generating Cross Fields for Quad Meshing
        112390, -- external Surface Reconstruction for 3D Gaussian Splatting via Local Structural
        112429, -- 2407.13342 Implicit Filtering for Learning Neural Signed Distance Functions from
        112455, -- 2409.14331 PISR: Polarimetric Neural Implicit Surface Reconstruction for Texturel
        112534, -- 2408.15524 Ray-Distance Volume Rendering for Neural Scene Reconstruction
        112660, -- external 3DFG-PIFu: 3D Feature Grids for Human Digitization from Sparse Views
        112792, -- 2409.03634 Surface-Centric Modeling for High-Fidelity Generalizable Neural Surfac
        112840, -- 2312.03357 RING-NeRF : Rethinking Inductive Biases for Versatile and Efficient Ne
        113081, -- external Coarse-to-Fine Implicit Representation Learning for 3D Hand-Object Rec
        113192, -- 2409.06710 McGrids: Monte Carlo-Driven Adaptive Grids for Iso-Surface Extraction
        113195, -- 2403.14619 ClusteringSDF: Self-Organized Neural Implicit Surfaces for 3D Decompos
        113235, -- 2401.03704 Sur^2f: A Hybrid Representation for High-Quality and Efficient Surface
        113419, -- 2407.12661 InfoNorm: Mutual Information Shaping of Normals for Sparse-View Recons
        113448, -- external Learning Neural Deformation Representation for 4D Dynamic Shape Genera
        113456, -- 2407.15554 Decomposition of Neural Discrete Representations for Large-Scale 3D Ma
        113470, -- external CPT-VR: Improving Surface Rendering via Closest Point Transform with V
        113576, -- 2506.10567 LRSLAM: Low-rank Representation of Signed Distance Fields in Dense Vis
        114364, -- external Algebraic Sphere Surface Fitting for Accurate and Efficient Mesh Recon
        115258, -- 2408.07325 RoCoSDF: Row-Column Scanned Neural Signed Distance Fields for Freehand
        115267, -- external SDFPlane: Explicit Neural Surface Reconstruction of Deformable Tissues
        115412, -- 2404.02614 Vestibular schwannoma growth prediction from longitudinal MRI by time-
        115502, -- 2404.02759 Unsupervised Occupancy Learning from Sparse Point Cloud
        115535, -- 2403.02561 Semantic Human Mesh Reconstruction with Textures
        115550, -- 2402.17062 HOISDF: Constraining 3D Hand-Object Pose Estimation with Global Signed
        115562, -- 2404.00149 VSRD: Instance-Aware Volumetric Silhouette Rendering for Weakly Superv
        115587, -- 2405.03388 3D LiDAR Mapping in Dynamic Environments using a 4D Implicit Neural Re
        115662, -- 2306.00519 DiffInDScene: Diffusion-based High-Quality 3D Indoor Scene Generation
        115785, -- 2404.00678 OmniSDF: Scene Reconstruction using Omnidirectional Signed Distance Fu
        116007, -- external LTM: Lightweight Textured Mesh Extraction and Refinement of Large Unbo
        116146, -- 2402.17364 Learning Dynamic Tetrahedra for High-Quality Talking Head Synthesis
        116272, -- 2312.02434 FINER: Flexible Spectral-bias Tuning in Implicit NEural Representation
        116518, -- 2311.11016 SNI-SLAM: Semantic Neural Implicit SLAM
        116566, -- 2312.02221 Slice3D: Multi-Slice Occlusion-Revealing Single View 3D Reconstruction
        116588, -- 2404.04876 HiLo: Detailed and Robust 3D Clothed Human Reconstruction with High-an
        116682, -- external Small Steps and Level Sets: Fitting Neural Surface Models with Point G
        116706, -- 2405.18131 Self-Supervised Dual Contouring
        116752, -- 2405.00340 NC-SDF: Enhancing Indoor Scene Reconstruction Using Neural SDFs with V
        116826, -- 2404.12383 G-HOP: Generative Hand-Object Prior for Interaction Reconstruction and
        116828, -- 2403.14366 SurroundSDF: Implicit 3D Scene Understanding Based on Signed Distance
        116920, -- 2311.12754 SelfOcc: Self-Supervised Vision-Based 3D Occupancy Prediction
        116928, -- 2403.20002 Grounding and Enhancing Grid-based Models for Neural Fields
        116999, -- external TurboSL: Dense Accurate and Fast 3D by Neural Inverse Structured Light
        117139, -- 2403.04198 CN-RMA: Combined Network with Ray Marching Aggregation for 3D Indoor O
        117162, -- 2312.02480 Differentiable Point-based Inverse Rendering
        117191, -- 2312.06740 MonoNPHM: Dynamic Head Reconstruction from Monocular Videos
        117251, -- 2602.03847 EventNeuS: 3D Mesh Reconstruction from a Single Event Camera
        117298, -- external Neural 4D Scene Reconstruction with Multiple One-Shot Scanning Systems
        117318, -- 2508.18213 Follow My Hold: Hand-Object Interaction Reconstruction through Geometr
        117323, -- external 1000FPS+ Novel View Synthesis from End-to-End Opaque Triangle Optimiza
        117394, -- 2606.20131 TriFlow: Generating Artist-Like 3D Mesh Topology via Nearest-Vertex Ve
        117421, -- external Parametric SDF for Dynamic Surface Reconstruction
        117579, -- 2511.16273 TetraSDF: Analytic Isosurface Extraction with Multi-resolution Tetrahe
        117612, -- 2604.01678 Director: Instance-aware Gaussian Splatting for Dynamic Scene Modeling
        117639, -- 2603.16085 Interact3D: Compositional 3D Generation of Interactive Objects
        117741, -- 2511.13431 FUSE: A Flow-based Mapping Between Shapes
        118089, -- 2606.31172 HSDF-Lane: Height-Aligned Signed Distance Field with Semantic Lane Pri
        118113, -- 2604.09100 Physically Grounded 3D Generative Reconstruction under Hand Occlusion
        118267, -- 2512.17773 Pix2NPHM: Learning to Regress NPHM Reconstructions From a Single Image
        119045, -- 2604.10415 Point2Pose: Occlusion-Recovering 6D Pose Tracking and 3D Reconstructio
        119711, -- 2410.15376 ActiveNeuS: Neural Signed Distance Fields for Active Stereo
        119713, -- 2302.03594 NICER-SLAM: Neural Implicit Scene Encoding for RGB SLAM
        119718, -- 2406.09801 RaNeuS: Ray-adaptive Neural Surface Reconstruction
        119723, -- 2308.06962 Color-NeuS: Reconstructing Neural Implicit Surfaces with Color
        119745, -- 2403.19985 Stable Surface Regularization for Fast Few-Shot NeRF
        119759, -- 2405.12006 Depth Reconstruction with Neural Signed Distance Fields in Structured
        119766, -- 2310.17632 DeepShaRM: Multi-View Shape and Reflectance Map Recovery Under Unknown
        119789, -- external PU-SDF: Arbitrary-Scale Uniformly Upsampling Point Clouds via Signed D
        119823, -- 2308.04868 InstantAvatar: Efficient 3D Head Reconstruction via Surface Rendering
        119857, -- 2501.01589 D^3-Human: Dynamic Disentangled Digital Human from Monocular Video
        119900, -- external High-Fidelity Lightweight Mesh Reconstruction from Point Clouds
        120031, -- 2506.13110 GS-2DGS: Geometrically Supervised 2DGS for Reflective Object Reconstru
        120246, -- external 3D-SLNR: A Super Lightweight Neural Representation for Large-scale 3D
        120526, -- 2305.17929 Factored-NeuS: Reconstructing Surfaces, Illumination, and Materials of
        120907, -- external Semantic Derivative Flow: Graph-Guided Diffusion for Controllable Inst
        120949, -- external Spatial-SAM: Spatially Consistent 3D Electron Microscopy Segmentation
        121910, -- 2605.29098 Seeing through boxes: Non-Line-of-Sight 3D Reconstruction from Radar S
        122622, -- 2609.36602 OTRetarget: Joint Robot and Object Motion Retargeting via Optimal Tran
        127417, -- 2605.10360 DySurface: Consistent 4D Surface Reconstruction via Bridging Explicit
        128802, -- 2605.29761 S2MDF: A Plug-And-Play Layer for Intersection-Free Multi-Object Signed
        129099, -- 2610.10197 VolCo: Volumetric Contact for High-Fidelity Human Grasp Generation
        129344  -- external Pygmalion: Bridging Reconstruction and Generation in Sparse Voxel-base
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
        5950, -- 2106.05779 Deep Implicit Surface Point Prediction Networks
        6445, -- 2108.08478 Learning Anchored Unsigned Distance Functions with Gradient Direction
        8781, -- 2204.09138 RangeUDF: Semantic Surface Reconstruction from 3D Point Clouds
        11616, -- 2211.14173 NeuralUDF: Learning Unsigned Distance Fields for Multi-view Reconstruc
        11710, -- 2211.16762 GeoUDF: Surface Reconstruction from 3D Point Clouds via Geometry-guide
        18357, -- 2307.09112 NU-MCC: Multiview Compressive Coding with Neighborhood Decoder and Rep
        19625, -- 2308.11441 Learning a More Continuous Zero Level Set in Unsigned Distance Fields
        23909, -- 2311.17050 Surf-D: Generating High-Quality Surfaces of Arbitrary Topologies Using
        25103, -- 2312.14140 HeadCraft: Modeling High-Detail Shape Variations for Animated 3DMMs
        26877, -- 2402.03654 Reviewing FID and SID Metrics on Generative Adversarial Networks
        28847, -- 2403.09326 HeadEvolver: Text to Head Avatars via Expressive and Attribute-Preserv
        33957, -- 2407.01330 A Lightweight UDF Learning Framework for 3D Reconstruction Based on Lo
        35106, -- 2407.16396 Learning Unsigned Distance Functions from Multi-view Images with Volum
        56523, -- 2603.05888 PixARMesh: Autoregressive Mesh-Native Single-View Scene Reconstruction
        63092, -- 2601.01005 Scale-aware Adaptive Supervised Network with Limited Medical Annotatio
        78520, -- 2309.08878 Surface Extraction from Neural Unsigned Distance Fields
        81040, -- 2010.13938 Neural Unsigned Distance Fields for Implicit Function Learning
        84934, -- 2603.16133 DualPrim: Compact 3D Reconstruction with Positive and Negative Primiti
        85448, -- 2604.22202 ArchSym: Detecting 3D-Grounded Architectural Symmetries in the Wild
        85583, -- 2605.19210 D-Convexity: A Unified Differentiable Convex Shape Prior via Quasi-Con
        86895, -- 2506.02938 MIND: Material Interface Generation from UDFs for Non-Manifold Surface
        86921, -- 2509.17212 High Resolution UDF Meshing via Iterative Networks
        90710, -- 2503.19458 GaussianUDF: Inferring Unsigned Distance Functions through 3D Gaussian
        100524, -- 2606.14415 CSPO: Constraint-Sensitive Policy Optimization for Safe Reinforcement
        101824, -- 2606.08957 Rethinking 3D Shape Generation: Diffusion over Superquadrics
        104768, -- 2605.02302 Structural MAT: Clean and Scalable Medial Axis Simplification via Expl
        107921, -- 2512.17781 LiteGE: Lightweight Geodesic Embedding for Efficient Geodesics Computa
        108135, -- 2503.23752 StrokeFusion: Vector Sketch Generation via Joint Stroke-UDF Encoding a
        113215, -- 2407.18381 Neural Surface Detection for Unsigned Distance Fields
        115959, -- 2403.01414 Unsigned Orthogonal Distance Fields: An Accurate Neural Implicit Repre
        116129, -- 2404.06851 UDiFF: Generating Conditional Unsigned Distance Fields with Optimal Wa
        116321, -- 2402.08876 DUDF: Differentiable Unsigned Distance Fields with Hyperbolic Scaling
        116325, -- 2303.15368 2S-UDF: A Novel Two-stage UDF Learning Method for Robust Non-watertigh
        116793, -- 2405.19295 3D Neural Edge Reconstruction
        117541, -- 2604.07337 From Blobs to Spokes: High-Fidelity Surface Reconstruction via Oriente
        118335, -- external PrimitiveUDF: Primitive-Based Unsigned Distance Fields for Surface Rec
        119311, -- 2606.31115 JacobianAvatar: Temporally Consistent Semi-rigid Avatar Reconstruction
        121739, -- external Distilling Unsigned Distance Function for Surface Reconstruction from
        127812, -- 2605.31466 VolFill: Single-View Amodal 3D Scene Reconstruction with Volumetric Fl
        128154  -- external Umbilic Multinomial Logistic Regression
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
        6060, -- 2106.10689 NeuS: Learning Neural Implicit Surfaces by Volume Rendering for Multi-
        9572, -- 2206.10885 KiloNeuS: A Versatile Neural Implicit Surface Representation for Real-
        11615, -- 2211.14086 ShadowNeuS: Neural SDF Reconstruction by Shadow Ray Supervision
        11907, -- 2212.05231 NeuS2: Fast Learning of Neural Implicit Surfaces for Multi-view Recons
        12007, -- 2212.08067 VolRecon: Volume Rendering of Signed Ray Distance Functions for Genera
        13487, -- 2303.02375 NeuDA: Neural Deformable Anchor for High-Fidelity Implicit Surface Rec
        13901, -- 2303.10840 Ref-NeuS: Ambiguity-Reduced Neural Implicit Surface Learning for Multi
        13996, -- 2303.12280 NLOS-NeuS: Non-line-of-sight Neural Implicit Surface
        14757, -- 2304.08706 Looking Through the Glass: Neural Surface Reconstruction Against High
        19221, -- 2308.07032 S3IM: Stochastic Structural SIMilarity and Its Unreasonable Effectiven
        20601, -- 2309.10336 Anti-Aliased Neural Implicit Surfaces with Encoding Level of Detail
        23464, -- 2311.10091 Adaptive Shells for Efficient Neural Radiance Field Rendering
        24173, -- 2312.01215 RNb-NeuS: Reflectance and Normal-based Multi-View 3D Reconstruction
        25166, -- 2312.15238 NoPose-NeuS: Jointly Optimizing Camera Poses with Neural Implicit Surf
        50554, -- 2506.04115 Multi-view Surface Reconstruction Using Normal and Reflectance Cues
        76739, -- 2407.12207 NeuSurfEmb: A Complete Pipeline for Dense Correspondence-based 6D Obje
        88059, -- 2506.23854 HiNeuS: High-fidelity Neural Surface Mitigating Low-texture and Reflec
        90755, -- 2403.10344 ViiNeuS: Volumetric Initialization for Implicit Neural Surface Reconst
        96343, -- 2509.20681 Efficient Construction of Implicit Surface Models from a Single Image
        113217, -- 2408.02079 Improving Neural Surface Reconstruction with Feature Priors from Multi
        115848, -- external MVCPS-NeuS: Multi-view Constrained Photometric Stereo for Neural Surfa
        117251, -- 2602.03847 EventNeuS: 3D Mesh Reconstruction from a Single Event Camera
        117274, -- 2505.10827 NeuSEditor: From Multi-View Images to Text-Guided Neural Surface Edits
        117277, -- 2501.03932 J-NeuS: Joint field optimization for Neural Surface reconstruction in
        119711, -- 2410.15376 ActiveNeuS: Neural Signed Distance Fields for Active Stereo
        119718, -- 2406.09801 RaNeuS: Ray-adaptive Neural Surface Reconstruction
        119723, -- 2308.06962 Color-NeuS: Reconstructing Neural Implicit Surfaces with Color
        120526, -- 2305.17929 Factored-NeuS: Reconstructing Surfaces, Illumination, and Materials of
        121166, -- external ManifoldNeuS: Manifold-aware View Optimizability for Pose-Free Neural
        121540  -- external Opti-NeuS: Neural Reconstruction for Dual-Layered Transparent and Opaq
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
        6082, -- 2106.11795 DeepMesh: Differentiable Iso-Surface Extraction
        7368, -- 2112.00724 RegNeRF: Regularizing Neural Radiance Fields for View Synthesis from S
        7509, -- 2112.07945 Efficient Geometry-aware 3D Generative Adversarial Networks
        7607, -- 2112.13592 Multimodal Image Synthesis and Editing: The Generative AI Era
        8781, -- 2204.09138 RangeUDF: Semantic Surface Reconstruction from 3D Point Clouds
        8950, -- 2205.02836 Neural 3D Scene Reconstruction with the Manhattan-world Assumption
        9023, -- 2205.07058 RTMV: A Ray-Traced Multi-View Synthetic Dataset for Novel View Synthes
        9218, -- 2205.13524 PREF: Phasorial Embedding Fields for Compact Neural Representations
        9298, -- 2205.15768 SAMURAI: Shape And Material from Unconstrained Real-world Arbitrary Im
        9481, -- 2206.07255 GRAM-HD: 3D-Consistent Image Generation at High Resolution with Genera
        9560, -- 2206.10535 EpiGRAF: Rethinking training of 3D GANs
        9842, -- 2207.09686 Object-Compositional Neural Implicit Surfaces
        10050, -- 2208.07227 DM-NeRF: 3D Scene Geometry Decomposition and Manipulation from 2D Imag
        10499, -- 2210.00124 Implicit Neural Spatial Representations for Time-dependent PDEs
        10507, -- 2210.00379 NeRF: Neural Radiance Field in 3D Vision, A Comprehensive Review
        10512, -- 2210.00647 IntrinsicNeRF: Learning Intrinsic Neural Radiance Fields for Editable
        10742, -- 2210.06108 Reconstructing Personalized Semantic Facial NeRF Models From Monocular
        10789, -- 2210.07181 MonoNeRF: Learning Generalizable NeRFs from Monocular Videos without C
        11016, -- 2210.13077 EpipolarNVS: leveraging on Epipolar geometry for single-image Novel Vi
        11513, -- 2211.12018 Level-S$^2$fM: Structure from Motion on Neural Level Set of Implicit S
        11616, -- 2211.14173 NeuralUDF: Learning Unsigned Distance Fields for Multi-view Reconstruc
        11755, -- 2212.00774 Score Jacobian Chaining: Lifting Pretrained 2D Diffusion Models for 3D
        11780, -- 2212.01331 Surface Normal Clustering for Implicit Representation of Manhattan Sce
        11789, -- 2212.01602 StegaNeRF: Embedding Invisible Information within Neural Radiance Fiel
        11971, -- 2212.07388 NoPe-NeRF: Optimising Neural Radiance Field with No Pose Prior
        12096, -- 2212.09802 Panoptic Lifting for 3D Scene Understanding with Neural Fields
        12224, -- 2212.13056 MonoNeRF: Learning a Generalizable Dynamic Radiance Field from Monocul
        12267, -- 2301.00157 Ponder: Point Cloud Pre-training via Neural Rendering
        12420, -- 2301.06782 A Large-Scale Outdoor Multi-modal Dataset and Benchmark for Novel View
        12435, -- 2301.07525 OmniObject3D: Large-Vocabulary 3D Object Dataset for Realistic Percept
        12788, -- 2302.01330 SceneDreamer: Unbounded 3D Scene Generation from 2D Image Collections
        12808, -- 2302.01571 Robust Camera Pose Refinement for Multi-Resolution Hash Encoding
        12957, -- 2302.04264 Nerfstudio: A Modular Framework for Neural Radiance Field Development
        13099, -- 2302.07224 Painting 3D Nature in 2D: View Synthesis of Natural Scenes from a Sing
        13228, -- 2302.10663 RealFusion: 360° Reconstruction of Any Object from a Single Image
        13287, -- 2302.12249 MERF: Memory-Efficient Radiance Fields for Real-time View Synthesis in
        13366, -- 2302.14340 HelixSurf: A Robust and Efficient Neural Implicit Surface Learning of
        13476, -- 2303.02091 Delicate Textured Mesh Recovery from NeRF via Adaptive Surface Refinem
        13733, -- 2303.07653 NEF: Neural Edge Fields for 3D Parametric Curve Reconstruction from Mu
        13783, -- 2303.08605 RICO: Regularizing the Unobservable for Indoor Compositional Reconstru
        13808, -- 2303.09036 Mimic3D: Thriving 3D-Aware GANs via 3D-to-2D Imitation
        13815, -- 2303.09152 Learning a Room with the Occ-SDF Hybrid: Signed Distance Function Ming
        13830, -- 2303.09431 NeRFMeshing: Distilling Neural Radiance Fields into Geometrically-Accu
        13898, -- 2303.10709 NeRF-LOAM: Neural Implicit Representation for Large-Scale Incremental
        13924, -- 2303.11219 NeTO:Neural Reconstruction of Transparent Objects with Self-Occlusion
        13981, -- 2303.12012 NeAT: Learning Neural Implicit Surfaces with Arbitrary Topologies from
        14034, -- 2303.12965 Efficient Meshy Neural Fields for Animatable Human Avatars
        14037, -- 2303.13022 ENVIDR: Implicit Differentiable Renderer with Neural Environment Light
        14084, -- 2303.13825 HandNeRF: Neural Radiance Fields for Animatable Interacting Hands
        14087, -- 2303.13855 Deformable Model-Driven Neural Rendering for High-Fidelity 3D Reconstr
        14088, -- 2303.13873 Fantasia3D: Disentangling Geometry and Appearance for High-quality Tex
        14103, -- 2303.14158 BundleSDF: Neural 6-DoF Tracking and 3D Reconstruction of Unknown Obje
        14104, -- 2303.14167 UrbanGIRAFFE: Representing Urban Scenes as Compositional Generative Ne
        14218, -- 2303.15951 F$^{2}$-NeRF: Fast Neural Radiance Field Training with Free Camera Tra
        14228, -- 2303.16184 VMesh: Hybrid Volume-Mesh Representation for Efficient View Synthesis
        14255, -- 2303.16617 NeFII: Inverse Rendering for Reflectance Decomposition with Near-Field
        14287, -- 2303.17147 NeILF++: Inter-Reflectable Light Fields for Geometry and Material Esti
        14321, -- 2303.17606 AvatarCraft: Transforming Text into Neural Human Avatars with Paramete
        14325, -- 2303.17712 S-VolSDF: Sparse Multi-View Stereo Regularization of Neural Implicit S
        14336, -- 2303.17905 3D-aware Image Generation using 2D Diffusion Models
        14339, -- 2303.17968 VDN-NeRF: Resolving Shape-Radiance Ambiguity via View-Dependence Norma
        14392, -- 2304.00916 DreamAvatar: Text-and-Shape Guided 3D Human Avatar Generation via Diff
        14422, -- 2304.01480 FineRecon: Depth-aware Feed-forward Network for Detailed 3D Reconstruc
        14492, -- 2304.02797 DeLiRa: Self-Supervised Depth, Light, and Radiance Fields
        14557, -- 2304.04278 Point-SLAM: Dense Neural Point Cloud-based SLAM
        14759, -- 2304.08757 NeAI: A Pre-convoluted Representation for Plug-and-Play Neural Ambient
        14822, -- 2304.09987 Tetra-NeRF: Representing Neural Radiance Fields Using Tetrahedra
        14978, -- 2304.13445 Neural-PBIR Reconstruction of Shape, Material, and Illumination
        15152, -- 2305.01643 Neural LiDAR Fields for Novel View Synthesis
        15188, -- 2305.02312 AG3D: Learning to Generate 3D Avatars from 2D Image Collections
        15236, -- 2305.03040 TUVF: Learning Generalizable Texture UV Radiance Fields
        15306, -- 2305.04268 Multi-Space Neural Radiance Fields
        15348, -- 2305.04966 NerfAcc: Efficient Sampling Accelerates NeRFs
        15572, -- 2305.08810 AutoRecon: Automated 3D Object Discovery and Reconstruction
        15806, -- 2305.11870 Chupa: Carving 3D Clothed Humans from Skinned Shape Priors using 2D Di
        16691, -- 2305.20082 Control4D: Efficient 4D Portrait Editing with Text
        16849, -- 2306.01405 Learning Signed Distance Functions from Noisy 3D Point Clouds via Nois
        16995, -- 2306.03092 Neuralangelo: High-Fidelity Neural Surface Reconstruction
        17220, -- 2306.05872 Neural Haircut: Prior-Guided Strand-Based Hair Reconstruction
        17230, -- 2306.06044 GANeRF: Leveraging Discriminators to Optimize Neural Radiance Fields
        17465, -- 2306.09109 NAVI: Category-Agnostic Image Collections with High-Quality 3D Shape a
        17488, -- 2306.09322 Neural Relighting with Subsurface Scattering by Learning the Radiance
        17537, -- 2306.09864 AvatarBooth: High-Quality and Customizable 3D Human Avatar Generation
        17547, -- 2306.10003 C2F2NeUS: Cascade Cost Frustum Fusion for High Fidelity and Generaliza
        17665, -- 2306.12422 DreamTime: An Improved Optimization Strategy for Diffusion-Guided 3D G
        17711, -- 2306.13455 DreamEditor: Text-Driven 3D Scene Editing with Neural Fields
        17883, -- 2306.16928 One-2-3-45: Any Single Image to 3D Mesh in 45 Seconds without Per-Shap
        17916, -- 2306.17723 FlipNeRF: Flipped Reflection Rays for Few-shot Novel View Synthesis
        17924, -- 2306.17843 Magic123: One Image to High-Quality 3D Object Generation Using Both 2D
        18146, -- 2307.05000 Neural Point-based Volumetric Avatar: Surface-guided Neural Points for
        18167, -- 2307.05473 Differentiable Blocks World: Qualitative 3D Decomposition by Rendering
        18285, -- 2307.08093 Cross-Ray Neural Radiance Fields for Novel-view Synthesis from Unconst
        18420, -- 2307.10173 DNA-Rendering: A Diverse Neural Actor Repository for High-Fidelity Hum
        18458, -- 2307.10776 Urban Radiance Field Representation with Deformable Neural Mesh Primit
        18497, -- 2307.11335 Tri-MipRF: Tri-Mip Representation for Efficient Anti-Aliasing Neural R
        18638, -- 2307.13908 Points-to-3D: Bridging the Gap between Sparse Points and Shape-Control
        18685, -- 2307.14620 NeRF-Det: Learning Geometry-Aware Volumetric Representation for Multi-
        18721, -- 2307.15131 Seal-3D: Interactive Pixel-Level Editing for Neural Radiance Fields
        18732, -- 2307.15333 Dynamic PlenOctree for Adaptive Sampling Refinement in Explicit NeRF
        18901, -- 2308.01898 UniSim: A Neural Closed-Loop Sensor Simulator
        18952, -- 2308.02840 Learning Unified Decompositional and Compositional NeRF for Editable N
        18980, -- 2308.03280 Mirror-NeRF: Learning Neural Radiance Fields for Mirrors with Whitted-
        19106, -- 2308.05371 Flexible Isosurface Extraction for Gradient-Based Mesh Optimization
        19247, -- 2308.07391 PARIS: Part-level Reconstruction and Motion Analysis for Articulated O
        19279, -- 2308.07868 ObjectSDF++: Improved Object-Compositional Neural Implicit Surfaces
        19288, -- 2308.07926 CoDeF: Content Deformation Fields for Temporally Consistent Video Proc
        19421, -- 2308.09591 O$^2$-Recon: Completing 3D Reconstruction of Occluded Objects in the S
        19448, -- 2308.09865 A Theory of Topological Derivatives for Inverse Rendering of Geometry
        19481, -- 2308.10089 Root Pose Decomposition Towards Generic Non-rigid 3D Reconstruction wi
        19580, -- 2308.10899 TADA! Text to Animatable Digital Avatars
        19585, -- 2308.11025 Coordinate Quantized Neural Implicit Representations for Multi-view Re
        19597, -- 2308.11130 Efficient View Synthesis with Neural Radiance Distribution Field
        19605, -- 2308.11198 Novel-view Synthesis and Pose Estimation for Hand-Object Interaction f
        19625, -- 2308.11441 Learning a More Continuous Zero Level Set in Unsigned Distance Fields
        19757, -- 2308.12967 NeO 360: Neural Fields for Sparse View Synthesis of Outdoor Scenes
        19770, -- 2308.13175 GridPull: Towards Scalability in Learning Implicit Representations fro
        19774, -- 2308.13223 EfficientDreamer: High-Fidelity and Robust 3D Creation via Orthogonal-
        19789, -- 2308.13404 Relighting Neural Radiance Fields with Shadow and Highlight Hints
        19831, -- 2308.14078 Sparse3D: Distilling Multiview-Consistent Diffusion for Object Reconst
        19859, -- 2308.14383 Multi-Modal Neural Radiance Field for Monocular Dense SLAM with a Ligh
        19893, -- 2308.15049 Pose-Free Neural Radiance Fields via Implicit Pose Regularization
        19915, -- 2308.15461 Canonical Factors for Hybrid Neural Fields
        19922, -- 2308.15536 DebSDF: Delving into the Details and Bias of Neural Indoor Scene Recon
        20112, -- 2309.02102 Iterative Superquadric Recomposition of 3D Objects from Multiple Views
        20133, -- 2309.02436 GO-SLAM: Global Optimization for Consistent 3D Instant Reconstruction
        20159, -- 2309.03160 ResFields: Residual Neural Fields for Spatiotemporal Signals
        20175, -- 2309.03453 SyncDreamer: Generating Multiview-consistent Images from a Single-view
        20225, -- 2309.04410 DeformToon3D: Deformable 3D Toonification from Neural Radiance Fields
        20232, -- 2309.04581 Dynamic Mesh-Aware Radiance Fields
        20247, -- 2309.04814 Speech2Lip: High-fidelity Speech to Lip Generation by Learning from a
        20293, -- 2309.05527 ReSimAD: Zero-Shot 3D Domain Transfer for Autonomous Driving with Sour
        20301, -- 2309.05663 Diffusion-Guided Reconstruction of Everyday Hand-Object Interaction Cl
        20437, -- 2309.07921 OpenIllumination: A Multi-Illumination Dataset for Inverse Rendering E
        20490, -- 2309.08596 Robust e-NeRF: NeRF from Sparse & Noisy Events under Non-Uniform Motio
        20561, -- 2309.09739 Improving Neural Indoor Surface Reconstruction with Mask-Guided Adapti
        20623, -- 2309.10684 Locally Stylized Neural Radiance Fields
        20811, -- 2309.13101 Deformable 3D Gaussians for High-Fidelity Monocular Dynamic Scene Reco
        20931, -- 2309.14872 Directional Texture Editing for 3D Models
        20949, -- 2309.15164 3D Reconstruction with Generalizable Neural Fields using Scene Priors
        21058, -- 2309.16859 Preface: A Data-driven Volumetric Prior for Few-shot Ultra High-resolu
        21252, -- 2310.01406 HumanNorm: Learning Normal Diffusion Model for High-quality and Realis
        21254, -- 2310.01410 LEAP: Liberate Sparse-view 3D Modeling from Camera Poses
        21628, -- 2310.05524 Parameterization-driven Neural Surface Reconstruction for Object-orien
        21637, -- 2310.05717 STOPNet: Multiview-based 6-DoF Suction Detection for Transparent Objec
        21698, -- 2310.06275 High-Fidelity 3D Head Avatars Reconstruction through Spatially-Varying
        21794, -- 2310.07449 PoRF: Pose Residual Field for Accurate Neural Surface Reconstruction
        21849, -- 2310.08092 Consistent123: Improve Consistency for One Image to 3D Object Synthesi
        21878, -- 2310.08370 UniPAD: A Universal Pre-training Paradigm for Autonomous Driving
        21913, -- 2310.08586 PonderV2: Pave the Way for 3D Foundation Model with A Universal Pre-tr
        22146, -- 2310.11696 MOHO: Learning Single-view Hand-held Object Reconstruction with Multi-
        22154, -- 2310.11784 Progressive3D: Progressively Local Editing for Text-to-3D Content Crea
        22204, -- 2310.12474 Enhancing High-Resolution 3D Generation through Pixel-wise Gradient Cl
        22356, -- 2310.14487 VQ-NeRF: Vector Quantization Enhances Implicit Neural Representations
        22406, -- 2310.15008 Wonder3D: Single Image to 3D using Cross-Domain Diffusion
        22427, -- 2310.15168 Ghost on the Shell: An Expressive Representation of General 3D Shapes
        22566, -- 2310.16818 DreamCraft3D: Hierarchical 3D Generation with Bootstrapped Diffusion P
        22586, -- 2310.17075 HyperFields: Towards Zero-Shot Generation of NeRFs from Text
        22760, -- 2310.19629 RayDF: Neural Ray-surface Distance Fields with Multi-view Consistency
        22853, -- 2311.00457 Single-view 3D Scene Reconstruction with High-fidelity Shape and Textu
        23449, -- 2311.09806 EvaSurf: Efficient View-Aware Implicit Textured Surface Reconstruction
        23569, -- 2311.12024 PF-LRM: Pose-Free Large Reconstruction Model for Joint Pose and Shape
        23582, -- 2311.12198 PhysGaussian: Physics-Integrated 3D Gaussians for Generative Dynamics
        23616, -- 2311.12775 SuGaR: Surface-Aligned Gaussian Splatting for Efficient 3D Mesh Recons
        23658, -- 2311.13297 Retargeting Visual Data with Deformation Fields
        23664, -- 2311.13398 Depth-Regularized Optimization for 3D Gaussian Splatting in Few-Shot I
        23767, -- 2311.15260 NeuRAD: Neural Rendering for Autonomous Driving
        23821, -- 2311.15980 Direct2.5: Diverse Text-to-3D Generation via Multi-view 2.5D Diffusion
        23825, -- 2311.16043 Relightable 3D Gaussians: Realistic Point Cloud Relighting with BRDF D
        23830, -- 2311.16096 Animatable and Relightable Gaussians for High-fidelity Human Avatar Mo
        23860, -- 2311.16499 InceptionHuman: Controllable Prompt-to-NeRF for Photorealistic 3D Huma
        23912, -- 2311.17061 HumanGaussian: Text-Driven 3D Human Generation with Gaussian Splatting
        23998, -- 2311.17971 GeoDream: Disentangling 2D and Geometric Priors for High-Fidelity and
        24045, -- 2311.18729 Portrait4D: Learning One-Shot 4D Head Avatar Synthesis using Synthetic
        24077, -- 2312.00093 GraphDreamer: Compositional 3D Scene Synthesis from Scene Graphs
        24079, -- 2312.00109 Scaffold-GS: Structured 3D Gaussians for View-Adaptive Rendering
        24172, -- 2312.01196 Neural Parametric Gaussians for Monocular Non-Rigid Object Reconstruct
        24178, -- 2312.01305 ViVid-1-to-3: Novel View Synthesis with Video Diffusion Models
        24197, -- 2312.01663 Customize your NeRF: Adaptive Source Driven 3D Scene Editing via Local
        24232, -- 2312.02135 Fast View Synthesis of Casual Videos with Soup-of-Planes
        24241, -- 2312.02155 GPS-Gaussian: Generalizable Pixel-wise 3D Gaussian Splatting for Real-
        24244, -- 2312.02189 StableDreamer: Taming Noisy Score Distillation Sampling for Text-to-3D
        24250, -- 2312.02214 FlashAvatar: High-fidelity Head Avatar with Efficient Gaussian Embeddi
        24315, -- 2312.02973 GauHuman: Articulated Gaussian Splatting from Monocular Human Videos
        24336, -- 2312.03160 HybridNeRF: Efficient Neural Rendering via Adaptive Volumetric Surface
        24363, -- 2312.03611 DreamComposer: Controllable 3D Object Generation via Multi-View Condit
        24449, -- 2312.04527 Correspondences of the Third Kind: Camera Pose Estimation from Object
        24484, -- 2312.04803 SuperNormal: Neural Surface Reconstruction via Multi-View Normal Integ
        24497, -- 2312.04963 Text-to-3D Generation with Bidirectional Diffusion using both 2D and 3
        24504, -- 2312.05161 TriHuman : A Real-time and Controllable Tri-plane Representation for D
        24510, -- 2312.05210 IntrinsicAvatar: Physically Based Inverse Rendering of Dynamic Humans
        24523, -- 2312.05295 Disentangled Clothed Avatar Generation from Text Descriptions
        24558, -- 2312.05748 IL-NeRF: Incremental Learning for Neural Radiance Fields with Camera P
        24571, -- 2312.05984 Accurate Differential Operators for Hybrid Neural Fields
        24602, -- 2312.06575 EasyVolcap: Accelerating Neural Volumetric Video Research
        24617, -- 2312.06657 Learning Naturally Aggregated Appearance for Efficient 3D Editing
        24619, -- 2312.06661 UpFusion: Novel View Diffusion from Unposed Sparse View Observations
        24634, -- 2312.06725 EpiDiff: Enhancing Multi-View Synthesis via Localized Epipolar-Constra
        24673, -- 2312.07315 NVS-Adapter: Plug-and-Play Novel View Synthesis from a Single Image
        24698, -- 2312.07539 HeadArtist: Text-conditioned 3D Head Generation with Self Score Distil
        24700, -- 2312.07541 SMERF: Streamable Memory Efficient Radiance Fields for Real-Time Large
        24734, -- 2312.08344 FoundationPose: Unified 6D Pose Estimation and Tracking of Novel Objec
        24748, -- 2312.08568 NViST: In the Wild New View Synthesis from a Single Image with Transfo
        24776, -- 2312.08889 SEEAvatar: Photorealistic Text-to-3D Avatar Generation with Constraine
        24791, -- 2312.09069 PI3D: Efficient Text-to-3D Generation with Pseudo-Image Diffusion
        24804, -- 2312.09228 3DGS-Avatar: Animatable Avatars via Deformable 3D Gaussian Splatting
        24812, -- 2312.09249 ZeroRF: Fast Sparse View 360° Reconstruction with Zero Pretraining
        24821, -- 2312.09313 LatentEditor: Text Driven Local Editing of 3D Scenes
        24831, -- 2312.09527 TIFace: Improving Facial Reconstruction through Tensorial Radiance Fie
        24935, -- 2312.11461 GAvatar: Animatable 3D Gaussian Avatars with Implicit Mesh Learning
        24949, -- 2312.11537 FastSR-NeRF: Improving NeRF Efficiency on Consumer Devices with A Simp
        25053, -- 2312.13285 UniSDF: Unifying Neural Representations for High-Fidelity 3D Reconstru
        25073, -- 2312.13663 Free-Editor: Zero-shot Text-driven 3D Scene Editing
        25101, -- 2312.14132 DUSt3R: Geometric 3D Vision Made Easy
        25145, -- 2312.14937 SC-GS: Sparse-Controlled Gaussian Splatting for Editable Dynamic Scene
        25211, -- 2312.15980 HarmonyView: Harmonizing Consistency and Diversity in One-Image-to-3D
        25229, -- 2312.16218 Hyper-VolTran: Fast and Generalizable One-Shot Image to 3D Object Stru
        25281, -- 2312.17225 4DGen: Grounded 4D Content Generation with Spatial-temporal Consistenc
        25292, -- 2312.17250 iFusion: Inverting Diffusion for Pose-Free Reconstruction from Sparse
        25403, -- 2401.01173 En3D: An Enhanced Generative Model for Sculpting 3D Humans from 2D Syn
        25491, -- 2401.02411 What You See is What You GAN: Rendering Every Pixel for High-Fidelity
        25631, -- 2401.04728 Morphable Diffusion: 3D-Consistent Diffusion for Single-image Avatar C
        25824, -- 2401.07727 HexaGen3D: StableDiffusion is just one step away from Fast and Diverse
        25899, -- 2401.08809 Learning Implicit Representation for Reconstructing Articulated Object
        25911, -- 2401.08937 ICON: Incremental CONfidence for Joint Pose and Radiance Field Optimiz
        26000, -- 2401.10171 SHINOBI: Shape and Illumination using Neural Object Decomposition via
        26177, -- 2401.12561 EndoGaussian: Real-time Gaussian Splatting for Dynamic Endoscopic Scen
        26298, -- 2401.14354 Learning Robust Generalizable Radiance Field with Visibility and Featu
        26305, -- 2401.14398 pix2gestalt: Amodal Segmentation by Synthesizing Wholes
        26338, -- 2401.14828 TIP-Editor: An Accurate 3D Editor Following Both Text-Prompts And Imag
        26364, -- 2401.15318 Gaussian Splashing: Unified Particles for Versatile Motion Synthesis a
        26366, -- 2401.15348 AniDress: Animatable Loose-Dressed Avatar from Sparse Views Using Garm
        26390, -- 2401.15841 2L3: Lifting Imperfect Generated 2D Images into Accurate 3D
        26468, -- 2401.16764 BoostDream: Efficient Refining for High-Quality Text-to-3D Generation
        26519, -- 2401.17603 Topology-Aware Latent Diffusion for 3D Shape Generation
        26521, -- 2401.17664 Image Anything: Towards Reasoning-coherent and Training-free Multi-mod
        26526, -- 2401.17807 Advances in 3D Generation: A Survey
        26534, -- 2401.17895 ReplaceAnything3D:Text-Guided 3D Scene Editing with Compositional Neur
        26606, -- 2402.00867 AToM: Amortized Text-to-Mesh using 2D Diffusion
        26908, -- 2402.03908 EscherNet: A Generative Model for Scalable View Synthesis
        26986, -- 2402.04796 Mesh-based Gaussian Splatting for Real-time Large-scale Deformation
        26989, -- 2402.04829 NeRF as a Non-Distant Environment Emitter in Physics-based Inverse Ren
        27373, -- 2402.10128 GES: Generalized Exponential Splatting for Efficient Radiance Field Re
        27397, -- 2402.10403 Polyhedral Complex Derivation from Piecewise Trilinear Networks
        27610, -- 2402.12377 Binary Opacity Grids: Capturing Fine Geometric Detail for Mesh-Based V
        27636, -- 2402.12712 MVDiffusion++: A Dense High-resolution Multi-view Diffusion Model for
        27698, -- 2402.13255 How NeRFs and 3D Gaussian Splatting are Reshaping SLAM: a Survey
        27779, -- 2402.14253 MVD$^2$: Efficient Multiview 3D Reconstruction for Multiview Diffusion
        27817, -- 2402.14652 Cleaner Pretraining Corpus Curation with Neural Web Scraping
        27834, -- 2402.14792 Consolidating Attention Features for Multi-view Image Editing
        27936, -- 2402.15870 Spec-Gaussian: Anisotropic View-Dependent Appearance for 3D Gaussian S
        28037, -- 2402.17214 CharacterGen: Efficient 3D Character Generation from Single Images wit
        28057, -- 2402.17427 VastGaussian: Vast 3D Gaussians for Large Scene Reconstruction
        28176, -- 2402.18842 ViewFusion: Towards Multi-View Consistency via Interpolated Denoising
        28287, -- 2403.01058 Neural Field Classifiers via Target Encoding and Classification Loss
        28345, -- 2403.01807 ViewDiff: 3D-Consistent Image Generation with Text-to-Image Models
        28371, -- 2403.02234 3DTopia: Large Text-to-3D Generation Model with Hybrid Diffusion Prior
        28561, -- 2403.05034 CRM: Single Image to 3D Textured Mesh with Convolutional Reconstructio
        28622, -- 2403.06092 Is Vanilla MLP in Neural Radiance Field Enough for Few-shot View Synth
        28661, -- 2403.06738 V3D: Video Diffusion Models are Effective 3D Generators
        28723, -- 2403.07563 Learning Generalizable Feature Fields for Mobile Manipulation
        28742, -- 2403.07807 StyleGaussian: Instant 3D Style Transfer with Gaussian Splatting
        28813, -- 2403.08902 Envision3D: One Image to 3D with Anchor Views Interpolation
        28843, -- 2403.09236 Hyper-3DG: Text-to-3D Gaussian Generation via Hypergraph
        28900, -- 2403.09981 Controllable Text-to-3D Generation via Surface-Aligned Gaussian Splatt
        28919, -- 2403.10335 NECA: Neural Customizable Human Avatar
        28925, -- 2403.10395 Isotropic3D: Image-to-3D Generation Based on a Single CLIP Embedding
        28975, -- 2403.11056 Analytic-Splatting: Anti-Aliased 3D Gaussian Splatting via Analytic In
        28983, -- 2403.11131 Omni-Recon: Harnessing Image-based Rendering for General-Purpose Neura
        29049, -- 2403.11899 GNeRP: Gaussian-guided Neural Reconstruction of Reflective Objects wit
        29057, -- 2403.12010 VideoMV: Consistent Multi-View Generation Based on Large Video Generat
        29069, -- 2403.12032 Generic 3D Diffusion Adapter Using Controlled Multi-View Editing
        29092, -- 2403.12409 ComboVerse: Compositional 3D Assets Creation Using Spatially-Aware Dif
        29130, -- 2403.12906 TexDreamer: Towards Zero-Shot High-Fidelity 3D Human Texture Generatio
        29170, -- 2403.13289 Text-to-3D Shape Generation
        29270, -- 2403.14554 Gaussian Frosting: Editable Complex Radiance Fields with Real-Time Ren
        29388, -- 2403.16080 PKU-DyMVHumans: A Multi-View Video Benchmark for High-Fidelity Dynamic
        29396, -- 2403.16292 latentSplat: Autoencoding Variational Gaussians for Fast Generalizable
        29410, -- 2403.16481 REFRAME: Reflective Surface Real-Time Rendering for Mobile Devices
        29436, -- 2403.16964 GSDF: 3DGS Meets SDF for Improved Rendering and Reconstruction
        29456, -- 2403.17237 DreamPolisher: Towards High-Quality Text-to-3D Generation via Geometri
        29470, -- 2403.17607 Fully-fused Multi-Layer Perceptrons on Intel Data Center GPUs
        29495, -- 2403.17888 2D Gaussian Splatting for Geometrically Accurate Radiance Fields
        29527, -- 2403.18241 NeuSDFusion: A Spatial-Aware Generative Model for 3D Shape Completion,
        29563, -- 2403.18795 Gamba: Marry Gaussian Splatting with Mamba for single view 3D reconstr
        29570, -- 2403.18820 MetaCap: Meta-learning Priors from Multi-View Imagery for Sparse-view
        29600, -- 2403.19319 Mesh2NeRF: Direct Mesh Supervision for Neural Radiance Field Represent
        29756, -- 2404.00987 FlexiDreamer: Single Image-to-3D Generation with FlexiCubes
        29793, -- 2404.01300 NeRF-MAE: Masked AutoEncoders for Self-Supervised 3D Representation Le
        29834, -- 2404.01810 GS2Mesh: Surface Reconstruction from Gaussian Splatting via Novel Ster
        29854, -- 2404.02125 3D Congealing: 3D-Aware Image Alignment in the Wild
        29962, -- 2404.03650 OpenNeRF: Open Set 3D Neural Scene Segmentation with Pixel-Wise Featur
        29964, -- 2404.03656 MVD-Fusion: Single-view 3D via Depth-consistent Multi-view Generation
        29965, -- 2404.03658 Know Your Neighbors: Improving Single-View Reconstruction via Spatial
        30011, -- 2404.04421 PhysAvatar: Learning the Physics of Dressed 3D Avatars from Visual Obs
        30154, -- 2404.06507 Reconstructing Hand-Held Objects in 3D from Images and Videos
        30256, -- 2404.07991 GoMAvatar: Efficient Animatable Human Modeling from Monocular Video Us
        30268, -- 2404.08252 MonoPatchNeRF: Improving Neural Radiance Fields with Patch-based Monoc
        30455, -- 2404.11151 REACTO: Reconstructing Articulated Objects from a Single Video
        30462, -- 2404.11256 MMCBE: Multi-modality Dataset for Crop Biomass Prediction and Beyond
        30480, -- 2404.11613 InFusion: Inpainting 3D Gaussians via Learning Depth Completion from D
        30538, -- 2404.12378 6Img-to-3D: Few-Image Large-Scale Outdoor Driving Scene Reconstruction
        30540, -- 2404.12385 MeshLRM: Large Reconstruction Model for High-Quality Meshes
        30847, -- 2404.17774 High-quality Surface Reconstruction using Gaussian Surfels
        30947, -- 2404.19760 Lightplane: Highly-Scalable Components for Neural 3D Fields
        30997, -- 2405.00954 X-Oscar: A Progressive Framework for High-quality Text-guided 3D Anima
        31269, -- 2405.08054 Coin3D: Controllable and Interactive 3D Assets Generation with Proxy-G
        31340, -- 2405.09874 Dual3D: Efficient and Consistent Text-to-3D Generation with Dual-mode
        31401, -- 2405.11252 Dreamer XL: Towards High-Resolution Text-to-3D Generation via Trajecto
        31628, -- 2405.14847 Neural Directional Encoding for Efficient and Accurate View-Dependent
        31802, -- 2405.16822 Vidu4D: Single Generated Video to High-Fidelity 4D Reconstruction with
        31811, -- 2405.16888 Part123: Part-aware 3D Reconstruction from a Single-view Image
        31955, -- 2405.18515 Atlas3D: Physically Constrained Self-Supporting Text-to-3D for Simulat
        32032, -- 2405.19678 View-Consistent Hierarchical 3D Segmentation Using Ultrametric Feature
        32084, -- 2405.20283 TetSphere Splatting: Representing High-Quality Geometry with Lagrangia
        32098, -- 2405.20343 Unique3D: High-Quality and Efficient 3D Mesh Generation from a Single
        32110, -- 2405.20510 Physically Compatible 3D Object Modeling from a Single Image
        32179, -- 2406.00440 Topo4D: Topology-Preserving Gaussian Splatting for High-Fidelity 4D He
        32365, -- 2406.03184 Ouroboros3D: Image-to-3D Generation via 3D-aware Recursive Diffusion
        32437, -- 2406.04254 GeoGen: Geometry-Aware Generative Modeling via Signed Distance Functio
        32557, -- 2406.05649 GTR: Improving Large 3D Reconstruction Models through Geometry and Tex
        32642, -- 2406.06527 IllumiNeRF: 3D Relighting Without Inverse Rendering
        32785, -- 2406.08176 Category-level Neural Field for Reconstruction of Partially Observed O
        32835, -- 2406.08759 GaussianForest: Hierarchical-Hybrid 3D Gaussian Splatting for Compress
        32845, -- 2406.08894 OpenMaterial: A Comprehensive Dataset of Complex Materials for 3D Reco
        32850, -- 2406.08960 AirPlanes: Accurate Plane Estimation via 3D-Consistent Embeddings
        33360, -- 2406.13897 CLAY: A Controllable Large-scale Generative Model for Creating High-qu
        33604, -- 2406.16815 ClotheDreamer: Text-Guided Garment Generation with 3D Gaussians
        33615, -- 2406.16864 StableNormal: Reducing Diffusion Variance for Stable and Sharp Normal
        33645, -- 2406.17345 NerfBaselines: Consistent and Reproducible Evaluation of Novel View Sy
        33665, -- 2406.17601 Director3D: Real-world Camera Trajectory and 3D Scene Generation from
        33751, -- 2406.18544 GS-ROR$^2$: Bidirectional-guided 3DGS and SDF for Reflective Object Re
        33827, -- 2406.19568 What Matters in Detecting AI-Generated Videos like Sora?
        34052, -- 2407.02445 Meta 3D AssetGen: Text-to-Mesh Generation with High-Quality Geometry,
        34065, -- 2407.02599 Meta 3D Gen
        34377, -- 2407.06938 RodinHD: High-Fidelity 3D Avatar Generation with Diffusion Models
        34394, -- 2407.07090 3D Gaussian Ray Tracing: Fast Tracing of Particle Scenes
        34584, -- 2407.09679 Physics-Informed Learning of Characteristic Trajectories for Smoke Rec
        34706, -- 2407.11174 iHuman: Instant Animatable Digital Humans From Monocular Videos
        34810, -- 2407.12395 Efficient Depth-Guided Urban View Synthesis
        34829, -- 2407.12667 SG-NeRF: Neural Surface Reconstruction with Scene Graph Optimization
        34963, -- 2407.14257 SparseCraft: Few-Shot Neural Reconstruction through Stereopsis Guided
        35017, -- 2407.15212 Surfel-based Gaussian Inverse Rendering for Fast and Relightable Dynam
        35077, -- 2407.15848 BoostMVSNeRFs: Boosting MVS-based NeRFs to Generalizable View Synthesi
        35106, -- 2407.16396 Learning Unsigned Distance Functions from Multi-view Images with Volum
        35141, -- 2407.16988 DreamCar: Leveraging Car-specific Prior for in-the-wild 3D Car Reconst
        35254, -- 2407.19108 ObjectCarver: Semi-automatic segmentation, reconstruction and separati
        35272, -- 2407.19542 UniVoxel: Fast Inverse Rendering by Unified Voxelization of Scene Repr
        35284, -- 2407.19774 Garment Animation NeRF with Color Editing
        35347, -- 2407.21002 XHand: Real-time Expressive Hand Avatar
        35592, -- 2408.03178 An Object is Worth 64x64 Pixels: Generating 3D Object via Image Diffus
        35797, -- 2408.06828 PIR: Photometric Inverse Rendering with Shading Cues Modeling and Surf
        35838, -- 2408.07540 3D Gaussian Editing with A Single Image
        35842, -- 2408.07595 Progressive Radiance Distillation for Inverse Rendering with Gaussian
        35927, -- 2408.09126 Barbie: Text to Barbie-Style 3D Avatars
        35980, -- 2408.10195 SpaRP: Fast 3D Object Reconstruction and Pose Estimation from Sparse V
        36072, -- 2408.11357 HumanCoser: Layered 3D Human Generation via Semantic-Aware Diffusion M
        36177, -- 2408.13149 Focus on Neighbors and Know the Whole: Towards Consistent Dense Multiv
        36186, -- 2408.13370 BiGS: Bidirectional Gaussian Primitives for Relightable 3D Gaussian Sp
        36340, -- 2408.15995 TEDRA: Text-based Editing of Dynamic and Photoreal Actors
        36345, -- 2408.16061 3D Reconstruction with Spatial Memory
        36510, -- 2409.01502 AMG: Avatar Motion Guided Video Generation
        36615, -- 2409.03456 LM-Gaussian: Boost Sparse-view 3D Gaussian Splatting with Large Model
        36746, -- 2409.06703 LEIA: Latent View-invariant Embeddings for Implicit 3D Articulation
        36808, -- 2409.08189 Gaussian Garments: Reconstructing Simulation-Ready Clothing with Photo
        37128, -- 2409.13591 Portrait Video Editing Empowered by Multimodal Generative Priors
        37334, -- 2409.17145 DreamWaltz-G: Expressive 3D Gaussian Avatars from Skeleton-Guided 2D D
        37496, -- 2409.19702 RNG: Relightable Neural Gaussians
        37534, -- 2409.20140 RISE-SDF: a Relightable Information-Shared Signed Distance Field for G
        37694, -- 2410.01804 EVER: Exact Volumetric Ellipsoid Rendering for Real-time View Synthesi
        37722, -- 2410.02103 MVGS: Multi-view-regulated Gaussian Splatting for Novel View Synthesis
        37778, -- 2410.02619 GI-GS: Global Illumination Decomposition on Gaussian Splatting for Inv
        37813, -- 2410.02764 Flash-Splat: 3D Reflection Removal with Flash Cues and Gaussian Splats
        37909, -- 2410.03825 MonST3R: A Simple Approach for Estimating Geometry in the Presence of
        38150, -- 2410.06756 DreamMesh4D: Video-to-4D Generation with Sparse-Controlled Gaussian-Me
        38268, -- 2410.08181 RGM: Reconstructing High-fidelity 3D Car Assets with Relightable 3D-GS
        38280, -- 2410.08208 SPA: 3D Spatial-Awareness Enables Effective Embodied Representation
        38321, -- 2410.08941 MeshGS: Adaptive Mesh-Aligned Gaussian Splatting for High-Quality Rend
        38456, -- 2410.10745 FlexGen: Flexible Multi-View Generation from Text and Image Inputs
        38767, -- 2410.13924 ARKit LabelMaker: A New Scale for Indoor 3D Scene Understanding
        39148, -- 2410.18974 3D-Adapter: Geometry-Consistent Multi-View Diffusion for High-Quality
        39222, -- 2410.20220 Neural Fields in Robotics: A Survey
        39479, -- 2411.00144 Self-Ensembling Gaussian Splatting for Few-Shot Novel View Synthesis
        39527, -- 2411.00771 CityGaussianV2: Efficient and Geometrically Accurate Reconstruction fo
        39574, -- 2411.01602 DreamPolish: Domain Score Distillation With Progressive Geometry Gener
        39840, -- 2411.06307 Acoustic Volume Rendering for Neural Impulse Response Fields
        39851, -- 2411.06525 I2VControl-Camera: Precise Video Camera Control with Adjustable Motion
        39855, -- 2411.06602 Adaptive and Temporally Consistent Gaussian Surfels for Multi-view Dyn
        39881, -- 2411.07135 Edify 3D: Scalable High-Quality 3D Asset Generation
        40073, -- 2411.10825 ARM: Appearance Reconstruction Model for Relightable 3D Generation
        40309, -- 2411.15018 Neural 4D Evolution under Large Topological Changes from 2D Images
        40403, -- 2411.16080 Boosting 3D Object Generation through PBR Materials
        40413, -- 2411.16185 Fancy123: One Image to High-Quality 3D Mesh Generation via Plug-and-Pl
        40471, -- 2411.16877 PreF3R: Pose-Free Feed-Forward 3D Gaussian Splatting from Variable-len
        40473, -- 2411.16898 G2SDF: Surface Reconstruction from Explicit Gaussians with Implicit SD
        40591, -- 2411.18311 Neural Surface Priors for Editable Gaussian Splatting
        40726, -- 2411.19950 AlphaTablets: A Generic Plane Representation for 3D Planar Reconstruct
        40946, -- 2412.03054 TREND: Unsupervised 3D Representation Learning via Temporal Forecastin
        40992, -- 2412.03558 MIDI: Multi-Instance Diffusion for Single Image to 3D Scene Generation
        41006, -- 2412.03632 MV-Adapter: Multi-view Consistent Image Generation Made Easy
        41038, -- 2412.04120 CrossSDF: 3D Reconstruction of Thin Structures From Cross-Sections
        41155, -- 2412.05278 Birth and Death of a Rose
        41163, -- 2412.05435 UniScene: Unified Occupancy-centric Driving Scene Generation
        41250, -- 2412.06767 MAtCha Gaussians: Atlas of Charts for High-Quality Geometry and Photor
        41301, -- 2412.07371 PRM: Photometric Stereo based Large Reconstruction Model
        41455, -- 2412.09401 SLAM3R: Real-Time Dense Scene Reconstruction from Monocular RGB Videos
        41626, -- 2412.11525 Sequence Matters: Harnessing Video Models in 3D Super-Resolution
        41694, -- 2412.12083 IDArb: Intrinsic Decomposition for Arbitrary Number of Input Views and
        41723, -- 2412.12507 3DGUT: Enabling Distorted Cameras and Secondary Rays in Gaussian Splat
        41816, -- 2412.13654 GAGS: Granularity-Aware Feature Distillation for Language Gaussian Spl
        41903, -- 2412.14939 GURecon: Learning Detailed 3D Geometric Uncertainties for Neural Surfa
        41958, -- 2412.15400 SolidGS: Consolidating Gaussian Surfel Splatting for Sparse-View Surfa
        42122, -- 2412.17812 FaceLift: Single Image to 3D Head with View Generation and GS-LRM
        42620, -- 2501.04631 Disentangled Clothed Avatar Generation with Layered Representation
        42864, -- 2501.08649 Joint Learning of Depth and Appearance for Portrait Image Animation
        42971, -- 2501.10283 GSTAR: Gaussian Surface Tracking and Reconstruction
        43075, -- 2501.12387 Continuous 3D Perception Model with Persistent State
        43217, -- 2501.14729 HERMES: A Unified Self-Driving World Model for Simultaneous 3D Scene U
        44354, -- 2502.11642 GaussianMotion: End-to-End Learning of Animatable Gaussian Avatars wit
        45093, -- 2502.19459 ArtGS: Building Interactable Replicas of Complex Articulated Objects v
        45203, -- 2502.20732 CADDreamer: CAD Object Generation from Single-view Images
        45413, -- 2503.02452 2DGS-Avatar: Animatable High-fidelity Clothed Avatar via 2D Gaussian S
        45490, -- 2503.03511 NeuGrasp: Generalizable Neural Surface Reconstruction with Background
        45728, -- 2503.06762 Gaussian RBFNet: Gaussian Radial Basis Functions for Fast and Accurate
        45797, -- 2503.07507 PE3R: Perception-Efficient 3D Reconstruction
        45856, -- 2503.08224 HRAvatar: High-Quality and Relightable Gaussian Head Avatar
        45893, -- 2503.08601 LiSu: A Dataset and Method for LiDAR Surface Normal Estimation
        46128, -- 2503.11172 Uncertainty-Aware Normal-Guided Gaussian Splatting for Surface Reconst
        46343, -- 2503.14483 Multi-view Reconstruction via SfM-guided Monocular Depth Estimation
        46363, -- 2503.14830 Decompositional Neural Scene Reconstruction with Generative Diffusion
        46562, -- 2503.17486 ProtoGS: Efficient and High-Quality Rendering with 3D Gaussian Prototy
        46585, -- 2503.17856 ClaraVid: A Holistic Scene Reconstruction Benchmark From Aerial Perspe
        46607, -- 2503.18073 PanopticSplatting: End-to-End Panoptic Gaussian Splatting
        46865, -- 2503.21694 Progressive Rendering Distillation: Adapting Stable Diffusion for Inst
        46871, -- 2503.21732 SparseFlex: High-Resolution and Arbitrary-Topology 3D Shape Modeling
        47091, -- 2504.00387 Scene4U: Hierarchical Layered 3D Scene Reconstruction from Single Pano
        48009, -- 2504.15278 DRAWER: Digital Reconstruction and Articulation With Environment Reali
        48364, -- 2505.02005 Learning Heterogeneous Mixture of Scene Experts for Large-scale Neural
        48376, -- 2505.02175 SparSplat: Fast Multi-View Reconstruction with Generalizable 2D Gaussi
        48378, -- 2505.02178 Sparfels: Fast Reconstruction from Sparse Unposed Imagery
        48562, -- 2505.05848 RefRef: A Synthetic Dataset and Benchmark for Reconstructing Refractiv
        48614, -- 2505.07003 CMD: Controllable Multiview Diffusion for 3D Editing and Progressive G
        48678, -- 2505.08239 ACT-R: Adaptive Camera Trajectories for Single View 3D Reconstruction
        49769, -- 2505.19754 NeuSym-RAG: Hybrid Neural Symbolic Retrieval with Multiview Structurin
        50470, -- 2506.02751 RobustSplat: Decoupling Densification and Dynamics for Transient-Free
        50513, -- 2506.03478 Facial Appearance Capture at Home with Patch-Level Reflectance Prior
        50525, -- 2506.03594 SplArt: Articulation Estimation and Part-Level Reconstruction with 3D
        50674, -- 2506.05573 PartCrafter: Structured 3D Mesh Generation via Compositional Latent Di
        50869, -- 2506.08640 Orientation Matters: Making 3D Generative Models Orientation-Aligned
        51019, -- 2506.10612 TexTailor: Customized Text-aligned Texturing via Effective Resampling
        51576, -- 2506.23207 TVG-SLAM: Robust Gaussian Splatting SLAM with Tri-view Geometric Const
        51736, -- 2507.05499 LoomNet: Enhancing Multi-View Image Generation via Latent Space Weavin
        51890, -- 2507.11061 Robust 3D-Masked Part-level Editing in 3D Gaussian Splatting with Regu
        52008, -- 2507.15629 Gaussian Splatting with Discretized SDF for Relightable Assets
        52024, -- 2507.16290 Dens3R: A Foundation Model for 3D Geometry Prediction
        52090, -- 2507.21045 Reconstructing 4D Spatial Intelligence: A Survey
        52119, -- 2507.23268 PixNerd: Pixel Neural Field Diffusion
        52125, -- 2507.23374 NeRF Is a Valuable Assistant for 3D Gaussian Splatting
        52286, -- 2508.06494 LightSwitch: Multi-view Relighting with Material-guided Diffusion
        52378, -- 2508.10893 STream3R: Scalable Sequential 3D Reconstruction with Causal Transforme
        52504, -- 2508.17811 MeshSplat: Generalizable Sparse-View Surface Reconstruction via Gaussi
        52644, -- 2509.03680 LuxDiT: Lighting Estimation with Video Diffusion Transformer
        52796, -- 2509.21245 Hunyuan3D-Omni: A Unified Framework for Controllable Generation of 3D
        52881, -- 2509.15123 RGB-Only Supervised Camera Parameter Optimization in Dynamic Scenes
        52946, -- 2509.18090 GeoSVR: Taming Sparse Voxels for Geometrically Accurate Surface Recons
        53282, -- 2510.05560 HoloScene: Simulation-Ready Interactive 3D Worlds from a Single Video
        53549, -- 2510.13678 FlashWorld: High-quality 3D Scene Generation within Seconds
        54667, -- 2512.07107 COREA: Coarse-to-Fine 3D Representation Alignment Between Relightable
        54937, -- 2512.19402 Real2Edit2Real: Generating Robotic Demonstrations via a 3D Control Int
        55121, -- 2601.03256 Muses: Designing, Composing, Generating Nonexistent Fantasy 3D Creatur
        55362, -- 2601.11514 ShapeR: Robust Conditional 3D Shape Generation from Casual Captures
        56718, -- 2603.02133 SimRecon: SimReady Compositional Scene Reconstruction from Real Videos
        56914, -- 2603.17735 TAPESTRY: From Geometry to Appearance via Consistent Turntable Videos
        58293, -- 2601.09211 Affostruction: 3D Affordance Grounding with Generative Reconstruction
        58895, -- 2603.25623 Accurate Surface and Reflectance Modelling from 3D Radar Data with Neu
        59055, -- 2603.21436 PAS3R: Pose-Adaptive Streaming 3D Reconstruction for Long Video Sequen
        61128, -- 2602.06226 ForeHOI: Feed-forward 3D Object Reconstruction from Daily Hand-Object
        61395, -- 2602.02741 PokeNet: Learning Kinematic Models of Articulated Objects from Human O
        62071, -- 2601.17835 Geometry-Grounded Gaussian Splatting
        62872, -- 2601.03782 PointWorld: Scaling 3D World Models for In-The-Wild Robotic Manipulati
        63348, -- 2512.21003 MVInverse: Feed-forward Multi-view Inverse Rendering in Seconds
        63436, -- 2512.19390 TwinAligner: Visual-Dynamic Alignment Empowers Physics-aware Real2Sim2
        63683, -- 2512.13680 LASER: Layer-wise Scale Alignment for Training-Free Streaming 4D Recon
        63840, -- 2512.10572 DeMapGS: Simultaneous Mesh Deformation and Surface Attribute Mapping v
        64302, -- 2512.01296 EGG-Fusion: Efficient 3D Reconstruction with Geometry-aware Gaussian S
        64641, -- 2511.18680 Inverse Rendering for High-Genus Surface Meshes from Multi-View Images
        64730, -- 2511.17364 SVRecon: Sparse Voxel Rasterization for Surface Reconstruction
        65077, -- 2511.10040 LoG3D: Ultra-High-Resolution 3D Shape Modeling via Local-to-Global Par
        65424, -- 2511.02483 OLATverse: A Large-scale Real-world Object Dataset with Precise Lighti
        65463, -- 2511.01767 Wonder3D++: Cross-domain Diffusion for High-fidelity 3D Generation fro
        65593, -- 2510.27234 MoRE: 3D Visual Geometry Reconstruction Meets Mixture-of-Experts
        65771, -- 2510.23930 PlanarGS: High-Fidelity Indoor 3D Gaussian Splatting Guided by Vision-
        66414, -- 2510.12971 Actron3D: Learning Actionable Neural Functions from Videos for Transfe
        66791, -- 2510.07190 MV-Performer: Taming Video Diffusion Model for Faithful and Synchroniz
        67058, -- 2510.02691 FSFSplatter: Build Surface and Novel Views with Sparse-Views within 2m
        68107, -- 2509.16423 3D Gaussian Flats: Hybrid 2D/3D Photometric Scene Reconstruction
        68136, -- 2509.15892 MoAngelo: Motion-Aware Neural Surface Reconstruction for Dynamic Scene
        68583, -- 2509.07493 Accurate and Complete Surface Reconstruction from 3D Gaussians via Dir
        68701, -- 2509.04966 Neuro-Spectral Architectures for Causal Physics-Informed Networks
        69339, -- 2508.15990 GelSLAM: A Real-time, High-Fidelity, and Robust 3D Tactile SLAM System
        69485, -- 2508.13537 EAvatar: Expression-Aware Head Avatar Reconstruction with Generative G
        70109, -- 2508.04508 Surf3R: Rapid Surface Reconstruction from Sparse RGB Views in Seconds
        70147, -- 2508.04099 DET-GS: Depth- and Edge-Aware Regularization for High-Fidelity 3D Gaus
        70295, -- 2508.02146 ScrewSplat: An End-to-End Method for Articulated Object Recognition
        70432, -- 2508.00366 SparseRecon: Neural Implicit Surface Reconstruction from Sparse Views
        70509, -- 2507.23162 Neural Multi-View Self-Calibrated Photometric Stereo without Photometr
        70517, -- 2507.23006 Robust and Efficient 3D Gaussian Splatting for Urban Scene Reconstruct
        70783, -- 2507.18255 LONG3R: Long Sequence Streaming 3D Reconstruction
        70797, -- 2507.18023 High-fidelity 3D Gaussian Inpainting: preserving multi-view consistenc
        71426, -- 2507.04004 Gaussian-LIC2: LiDAR-Inertial-Camera Gaussian Splatting SLAM
        71488, -- 2507.02363 LocalDyGS: Multi-view Global Dynamic Scene Modeling via Adaptive Local
        71574, -- 2507.00429 DiGA3D: Coarse-to-Fine Diffusional Propagation of Geometry and Appeara
        72044, -- 2506.10507 Edit360: 2D Image Edits to 3D Assets from Any Angle
        73271, -- 2504.20222 FreBIS: Frequency-Based Stratification for Neural Implicit Surface Rep
        73489, -- 2504.13204 EDGS: Eliminating Densification for Efficient Convergence of 3DGS
        73625, -- 2504.07144 GIGA: Generalizable Sparse Image-driven Gaussian Humans
        73942, -- 2503.16822 RigGS: Rigging of 3D Gaussians for Modeling Articulated Objects in Vid
        74478, -- 2502.18219 Synthesizing Consistent Novel Views via 3D Epipolar Attention without
        74735, -- 2502.08352 Sat-DN: Implicit Surface Reconstruction from Multi-View Satellite Imag
        74960, -- 2502.01157 Radiant Foam: Real-Time Differentiable Ray Tracing
        75062, -- 2501.18630 Deformable Beta Splatting
        75196, -- 2501.08174 Object-Centric 2D Gaussian Splatting: Background Removal and Occlusion
        75405, -- 2412.15215 EnvGS: Modeling View-Dependent Appearance with Environment Gaussian
        75457, -- 2412.11762 GS-ProCams: Gaussian Splatting-based Projector-Camera Systems
        75585, -- 2412.04459 Sparse Voxels Rasterization: Real-time High-fidelity Radiance Field Re
        75704, -- 2411.16820 DetailGen3D: Generative 3D Geometry Enhancement via Data-Dependent Flo
        76070, -- 2410.09771 EUGens: Efficient, Unified, and General Dense Layers
        76753, -- 2407.11419 TeethDreamer: 3D Teeth Reconstruction from Five Intra-oral Photographs
        77219, -- 2405.14580 LDM: Large Tensorial SDF Model for Textured Mesh Generation
        77264, -- 2405.10255 When LLMs step into the 3D World: A Survey and Meta-Analysis of 3D Tas
        77393, -- 2404.13921 NeRF-DetS: Enhanced Adaptive Spatial-wise Sampling and View-wise Fusio
        77428, -- 2404.10394 Portrait3D: Text-Guided High-Quality 3D Portrait Generation Using Pyra
        78491, -- 2309.12790 NTO3D: Neural Target Object 3D Reconstruction with Segment Anything
        78956, -- 2305.18832 ReTR: Modeling Rendering Via Transformer for Generalizable Neural Surf
        79223, -- 2303.10962 Neural Implicit Vision-Language Feature Fields
        82843, -- 2604.28196 HERMES++: Toward a Unified Driving World Model for 3D Scene Understand
        83698, -- 2605.23888 GenRecon: Bridging Generative Priors for Multi-View 3D Scene Reconstru
        84069, -- 2508.02443 PRIMU: Uncertainty Estimation for Novel Views in Gaussian Splatting fr
        84101, -- 2509.13938 Plug-and-Play PDE Optimization for 3D Gaussian Splatting: Toward High-
        84148, -- 2511.04029 Faithful Contouring: Near-Lossless 3D Voxel Representation Free from I
        84232, -- 2511.19172 MetroGS: Efficient and Stable Reconstruction of Geometrically Accurate
        84303, -- 2512.01329 TagSplat: Topology-Aware Gaussian Splatting for Dynamic Mesh Modeling
        84318, -- 2512.02664 PolarGuide-GSDR: 3D Gaussian Splatting Driven by Polarization Priors a
        84337, -- 2512.04076 Radiance Meshes for Volumetric Reconstruction
        84591, -- 2602.21105 BrepGaussian: CAD reconstruction from Multi-View Images with Gaussian
        84934, -- 2603.16133 DualPrim: Compact 3D Reconstruction with Positive and Negative Primiti
        84987, -- 2603.19682 3D Gaussian Splatting with Self-Constrained Priors for High Fidelity S
        85160, -- 2603.27151 DiffSoup: Direct Differentiable Rasterization of Triangle Soup for Ext
        85269, -- 2604.04063 4C4D: 4 Camera 4D Gaussian Splatting
        85274, -- 2604.04425 HandDreamer: Zero-Shot Text to 3D Hand Model Generation using Correcti
        85404, -- 2604.17082 D-Prism: Differentiable Primitives for Structured Dynamic Modeling
        85623, -- 2104.04532 Neural RGB-D Surface Reconstruction
        86224, -- 2501.16312 LinPrim: Linear Primitives for Differentiable Volumetric Rendering
        86275, -- 2506.11252 Anti-Aliased 2D Gaussian Splatting
        86748, -- 2509.20824 ARMesh: Autoregressive Mesh Generation via Next-Level-of-Detail Predic
        86885, -- 2506.05280 Unifying Appearance Codes and Bilateral Grids for Driving Scene Gaussi
        86893, -- 2507.02863 Point3R: Streaming 3D Reconstruction with Explicit Spatial Pointer Mem
        86895, -- 2506.02938 MIND: Material Interface Generation from UDFs for Non-Manifold Surface
        87629, -- 2502.12545 IM360: Large-scale Indoor Mapping with 360 Cameras
        87647, -- 2503.14786 SketchSplat: 3D Edge Reconstruction via Differentiable Multi-view Sket
        87668, -- 2412.12765 Monocular Facial Appearance Capture in the Wild
        87761, -- 2408.10789 Self-supervised Learning of Hybrid Part-aware 3D Representations of 2D
        87781, -- 2410.24204 GeoSplatting: Towards Geometry Guided Gaussian Splatting for Physicall
        87795, -- 2503.15897 Learning 3D Scene Analogies with Neural Contextual Scene Maps
        87864, -- 2411.16392 Quadratic Gaussian Splatting: High Quality Surface Reconstruction with
        87869, -- 2507.15602 SurfaceSplat: Connecting Surface Reconstruction and Gaussian Splatting
        87910, -- 2411.12981 GazeGaussian: High-Fidelity Gaze Redirection with 3D Gaussian Splattin
        87925, -- 2503.19914 Learning 3D Object Spatial Relationships from Pre-trained 2D Diffusion
        87931, -- 2508.09830 RayletDF: Raylet Distance Fields for Generalizable 3D Surface Reconstr
        87939, -- 2412.16919 TAR3D: Creating High-Quality 3D Assets via Next-Part Prediction
        87973, -- 2406.01593 MaGS: Reconstructing and Simulating Dynamic 3D Objects with Mesh-adsor
        87978, -- 2507.08416 InstaScene: Towards Complete 3D Instance Decomposition and Reconstruct
        88018, -- 2503.08407 WildSeg3D: Segment Any 3D Objects in the Wild from 2D Images
        88099, -- 2412.16776 DMesh++: An Efficient Differentiable Mesh for Complex Shapes
        88245, -- 2507.20200 Neural Shell Texture Splatting: More Details and Fewer Primitives
        88321, -- 2509.19726 PolGS: Polarimetric Gaussian Splatting for Fast Reflective Surface Rec
        88416, -- 2503.22349 GCRayDiffusion: Pose-Free Surface Reconstruction via Geometric Consist
        88420, -- 2506.23479 Instant GaussianImage: A Generalizable and Self-Adaptive Image Represe
        88478, -- 2505.05591 QuickSplat: Fast 3D Surface Reconstruction via Learned Gaussian Initia
        88502, -- 2508.03118 H3R: Hybrid Multi-view Correspondence for Generalizable 3D Reconstruct
        89105, -- 2506.06221 BiAssemble: Learning Collaborative Affordance for Bimanual Geometric A
        90210, -- 2503.18513 LookCloser: Frequency-aware Radiance Field for Tiny-Detail Scene
        90235, -- 2412.16028 CoCoGaussian: Leveraging Circle of Confusion for Gaussian Splatting fr
        90250, -- 2412.16361 Toward Robust Neural Reconstruction from Sparse Point Sets
        90255, -- 2412.10084 ProbeSDF: Light Field Probes For Neural Surface Reconstruction
        90262, -- 2504.19819 Joint Optimization of Neural Radiance Fields and Continuous Camera Mot
        90366, -- 2412.09545 SimAvatar: Simulation-Ready Avatars with Layered Hair and Clothing
        90379, -- 2503.19673 MultimodalStudio: A Heterogeneous Sensor Dataset and Framework for Neu
        90427, -- 2503.11143 GaussianIP: Identity-Preserving Realistic 3D Human Generation via Huma
        90428, -- 2504.20403 Creating Your Editable 3D Photorealistic Avatar with Tetrahedron-const
        90559, -- 2503.21816 EVPGS: Enhanced View Prior Guidance for Splatting-based Extrapolated V
        90590, -- 2411.18625 Textured Gaussians for Enhanced 3D Scene Appearance Modeling
        90592, -- 2409.02482 Volumetric Surfaces: Representing Fuzzy Geometries with Layered Meshes
        90600, -- 2503.11269 Prof. Robot: Differentiable Robot Rendering Without Static and Self-Co
        90604, -- 2411.19474 Blurred LiDAR for Sharper 3D: Robust Handheld 3D Scanning with Diffuse
        90650, -- 2503.03132 Dynamic Neural Surfaces for Elastic 4D Shape Representation and Analys
        90681, -- 2504.08541 Digital Twin Catalog: A Large-Scale Photorealistic 3D Object Digital T
        90687, -- 2503.15975 Acc3D: Accelerating Single Image to 3D Diffusion Models via Edge Consi
        90702, -- 2504.18509 Eval3D: Interpretable and Fine-grained Evaluation for 3D Generation
        90710, -- 2503.19458 GaussianUDF: Inferring Unsigned Distance Functions through 3D Gaussian
        90732, -- 2503.18361 NeRFPrior: Learning Neural Radiance Field as a Prior for Indoor Scene
        90741, -- 2503.21442 RainyGS: Efficient Rain Synthesis with Physically-Based Gaussian Splat
        90743, -- 2503.18363 MonoInstance: Enhancing Monocular Priors via Multi-view Instance Align
        90748, -- 2411.17067 Geometry Field Splatting with Gaussian Surfels
        90785, -- 2504.20026 LIRM: Large Inverse Rendering Model for Progressive Reconstruction of
        90855, -- 2504.20378 Sparse2DGS: Geometry-Prioritized Gaussian Splatting for Surface Recons
        90872, -- 2502.02187 ShapeShifter: 3D Variations Using Multiscale and Sparse Point-Voxel Di
        90895, -- 2503.00881 Evolving High-Quality Rendering and Reconstruction in a Unified Framew
        90897, -- 2501.06693 Vid2Sim: Realistic and Interactive Simulation from Video for Urban Nav
        90911, -- 2504.08410 PMNI: Pose-free Multi-view Normal Integration for Reflective and Textu
        90928, -- 2411.16718 Neuro-Symbolic Evaluation of Text-to-Video Models using Formal Verific
        90953, -- 2503.08382 Twinner: Shining Light on Digital Twins in a Few Snaps
        91430, -- 2406.16360 Inverse Rendering using Multi-Bounce Path Tracing and Reservoir Sampli
        92161, -- 2410.11682 SurFhead: Affine Rig Blending for Geometrically Accurate 2D Gaussian S
        92283, -- 2410.01202 AniSDF: Fused-Granularity Neural Surfaces with Anisotropic Encoding fo
        92443, -- 2409.16921 Moner: Motion Correction in Undersampled Radial MRI with Unsupervised
        93414, -- 2603.28090 To View Transform or Not to View Transform: NeRF-based Pre-training Pe
        94710, -- 2603.00413 DiffTrans: Differentiable Geometry-Materials Decomposition for Reconst
        94776, -- 2601.21400 Mesh Splatting for End-to-end Multiview Surface Reconstruction
        94925, -- 2602.02089 UrbanGS: Efficient and Scalable Architecture for Geometrically Accurat
        94931, -- 2412.03059 CLAP: Unsupervised 3D Representation Learning for Fusion 3D Perception
        95792, -- 2602.17101 Benchmarking the Effects of Object Pose Estimation and Reconstruction
        96122, -- 2411.15468 SplatSDF: Boosting SDF-NeRF Via Architecture-Level Fusion with Gaussia
        96244, -- 2511.01501 SE(3)-PoseFlow: Estimating 6D Pose Distributions for Uncertainty-Aware
        96518, -- 2502.02657 SiLVR: Scalable Lidar-Visual Radiance Field Reconstruction with Uncert
        96914, -- 2504.00159 SonarSplat: Novel View Synthesis of Imaging Sonar Via Gaussian Splatti
        97200, -- 2510.06754 UniFField: A Generalizable Unified Neural Feature Field for Visual, Se
        97680, -- 2411.13620 Robust SG-NeRF: Robust Scene Graph Aided Neural Surface Reconstruction
        98239, -- 2606.13644 Surflo: Consistent 3D Surface Flow Model with Global State
        99674, -- 2605.12494 Revisiting Photometric Ambiguity for Accurate Gaussian-Splatting Surfa
        101045, -- 2606.11913 From Content to Knowledge: Lightning Fast Long-Video Understanding wit
        101146, -- 2510.07442 INFER: Learning Implicit Neural Frequency Response Fields for Confined
        101381, -- 2506.24121 TextMesh4D: Zero-shot Text-to-4D Mesh Generation
        102630, -- 2607.06559 RynnWorld-4D: 4D Embodied World Models for Robotic Manipulation
        103914, -- 2405.19657 Uncertainty-guided Optimal Transport in Depth Supervised Sparse-View 3
        104190, -- 2211.12497 MagicPony: Learning Articulated 3D Animals in the Wild
        104781, -- 2601.19683 SharpNet: Enhancing MLPs to Represent Functions with Controlled Non-di
        104810, -- 2606.15238 HairLRM: Strand-based Hair Modeling via Large Reconstruction Models
        104817, -- 2605.06408 Scalable GPU Construction of 3D Voronoi and Power Diagrams
        104823, -- 2604.23537 Distance Field Rasterization for End-to-End Mesh Reconstruction
        104829, -- 2602.08198 PEGAsus: 3D Personalization of Geometry and Appearance
        104876, -- 2603.07664 Ref-DGS: Reflective Dual Gaussian Splatting
        105553, -- 2411.12510 PR-ENDO: Physically Based Relightable Gaussian Splatting for Endoscopy
        106424, -- 2509.18041 NeuS-QA: Grounding Long-Form Video Understanding in Temporal Logic and
        106621, -- 2511.22704 Splat-SAP: Feed-Forward Gaussian Splatting for Human-Centered Scene wi
        106757, -- 2511.08079 Deep Inverse Shading: Consistent Albedo and Surface Detail Recovery vi
        107152, -- 2601.04984 OceanSplat: Object-aware Gaussian Splatting with Trinocular View Consi
        107159, -- 2503.11368 PBR3DGen: A VLM-Guided Mesh Generation with High-Quality PBR Texture
        107874, -- 2511.14633 SparseSurf: Sparse-View 3D Gaussian Splatting for Surface Reconstructi
        107926, -- 2511.15102 Gaussian Blending: Rethinking Alpha Blending in 3D Gaussian Splatting
        108045, -- 2511.08310 NeuSpring: Neural Spring Fields for Reconstruction and Simulation of D
        108454, -- 2412.04826 Pushing Rendering Boundaries: Hard Gaussian Splatting
        108753, -- 2411.18966 SVGS: Enhancing Gaussian Splatting Using Primitives with Spatially Var
        109353, -- 2608.06117 Confidence matters: Leveraging Multi-view Geometric Priors for GS-base
        109856, -- 2305.14831 OD-NeRF: Efficient Training of On-the-Fly Dynamic Neural Radiance Fiel
        109858, -- 2411.19271 AGS-Mesh: Adaptive Gaussian Splatting and Meshing with Geometric Prior
        109862, -- 2502.13968 Betsu-Betsu: Multi-View Separable 3D Reconstruction of Two Interacting
        109866, -- 2404.09531 Oblique-MERF: Revisiting and Improving MERF for Oblique Photography
        109883, -- 2409.03061 Incorporating Dense Metric Depth into Neural 3D Representations for Vi
        109929, -- 2501.09259 OpticFusion: Multi-Modal Neural Implicit 3D Reconstruction of Microstr
        112184, -- 2509.18497 Differentiable Light Transport with Gaussian Surfels via Adapted Radio
        112187, -- 2506.24096 MILo: Mesh-In-the-Loop Gaussian Splatting for Detailed and Efficient S
        112195, -- 2509.21007 Marching Neurons: Accurate Surface Extraction for Neural Implicit Shap
        112354, -- 2505.20431 ART-DECO: Arbitrary Text Guidance for 3D Detailizer Construction
        112356, -- 2511.18873 Neural Texture Splatting: Expressive 3D Gaussian Splatting for View Sy
        112365, -- 2509.12721 SPGen: Spherical Projection as Consistent and Flexible Representation
        112455, -- 2409.14331 PISR: Polarimetric Neural Implicit Surface Reconstruction for Texturel
        112469, -- 2407.15686 Differentiable Convex Polyhedra Optimization from Multi-view Images
        112494, -- 2407.04699 LaRa: Efficient Large-Baseline Radiance Fields
        112526, -- 2408.03753 3iGS: Factorised Tensorial Illumination for 3D Gaussian Splatting
        112532, -- 2407.08221 GAURA: Generalizable Approach for Unified Restoration and Rendering of
        112534, -- 2408.15524 Ray-Distance Volume Rendering for Neural Scene Reconstruction
        112558, -- 2409.14778 Human Hair Reconstruction with Strand-Aligned 3D Gaussians
        112681, -- 2312.03795 AnimatableDreamer: Text-Guided Non-rigid 3D Model Generation and Recon
        112683, -- 2404.06119 DreamView: Injecting View-specific Text Guidance into Text-to-3D Gener
        112741, -- 2406.00609 SuperGaussian: Repurposing Video Models for 3D Super Resolution
        112743, -- 2407.13592 MeshFeat: Multi-Resolution Features for Neural Fields on Meshes
        112750, -- 2403.10166 SemanticHuman-HD: High Resolution Semantic disentangled 3D Human Gener
        112792, -- 2409.03634 Surface-Centric Modeling for High-Fidelity Generalizable Neural Surfac
        112840, -- 2312.03357 RING-NeRF : Rethinking Inductive Biases for Versatile and Efficient Ne
        112863, -- 2409.18953 UniCal: Unified Neural Sensor Calibration
        112874, -- 2506.08619 A Probability-guided Sampler for Neural Implicit Surface Rendering
        112878, -- 2403.14053 Leveraging Thermal Modality to Enhance Reconstruction in Low-Light Con
        112912, -- 2407.11962 Motion-Oriented Compositional Neural Radiance Fields for Monocular Dyn
        112931, -- 2312.04424 Cascade-Zero123: One Image to Highly Consistent 3D with Self-Prompted
        113050, -- 2409.15715 Disentangled Generation and Aggregation for Robust Radiance Fields
        113051, -- 2212.10950 UNIKD: UNcertainty-Filtered Incremental Knowledge Distillation for Neu
        113060, -- 2403.19160 Within the Dynamic Context: Inertia-aware 3D Human Modeling with Pose
        113138, -- 2311.16937 The Sky's the Limit: Relightable Outdoor Scenes via a Sky-pixel Constr
        113192, -- 2409.06710 McGrids: Monte Carlo-Driven Adaptive Grids for Iso-Surface Extraction
        113195, -- 2403.14619 ClusteringSDF: Self-Organized Neural Implicit Surfaces for 3D Decompos
        113234, -- 2312.11587 Relightable Neural Actor with Intrinsic Decomposition and Pose Control
        113235, -- 2401.03704 Sur^2f: A Hybrid Representation for High-Quality and Efficient Surface
        113259, -- 2408.05533 UAV First-Person Viewers Are Radiance Field Learners
        113293, -- 2312.02202 Volumetric Rendering with Baked Quadrature Fields
        113344, -- 2410.17839 Few-shot NeRF by Adaptive Rendering Loss Regularization
        113419, -- 2407.12661 InfoNorm: Mutual Information Shaping of Normals for Sparse-View Recons
        113456, -- 2407.15554 Decomposition of Neural Discrete Representations for Large-Scale 3D Ma
        113457, -- 2405.11921 MirrorGaussian: Reflecting 3D Gaussians for Reconstructing Mirror Refl
        113484, -- 2409.06923 Rethinking Directional Parameterization in Neural Implicit Surface Rec
        113692, -- 2404.06836 O2V-Mapping: Online Open-Vocabulary Mapping with Neural Implicit Repre
        114191, -- 2605.09644 Attention Itself Could Retrieve.RetrieveVGGT: Training-Free Long Conte
        114960, -- 2404.06128 Gaussian Pancakes: Geometrically-Regularized 3D Gaussian Splatting for
        115258, -- 2408.07325 RoCoSDF: Row-Column Scanned Neural Signed Distance Fields for Freehand
        115455, -- 2404.14044 HashPoint: Accelerated Point Searching and Sampling for Neural Renderi
        115463, -- 2403.16224 Inverse Rendering of Glossy Objects via the Neural Plenoptic Function
        115502, -- 2404.02759 Unsupervised Occupancy Learning from Sparse Point Cloud
        115562, -- 2404.00149 VSRD: Instance-Aware Volumetric Silhouette Rendering for Weakly Superv
        115576, -- 2307.00842 VINECS: Video-based Neural Character Skinning
        115615, -- 2312.15406 Objects as Volumes: A Stochastic Geometry View of Opaque Solids
        115624, -- 2312.02137 MANUS: Markerless Grasp Capture using Articulated 3D Gaussians
        115649, -- 2311.12194 DiffAvatar: Simulation-Ready Garment Optimization with Differentiable
        115758, -- 2403.17496 Dr.Hair: Reconstructing Scalp-Connected Hair Strands without Pre-Train
        115785, -- 2404.00678 OmniSDF: Scene Reconstruction using Omnidirectional Signed Distance Fu
        115796, -- 2403.11812 Aerial Lifting: Neural Urban Semantic and Building Instance Lifting fr
        115921, -- 2403.17801 Towards 3D Vision with Low-Cost Single-Photon Cameras
        115959, -- 2403.01414 Unsigned Orthogonal Distance Fields: An Accurate Neural Implicit Repre
        115988, -- 2403.19780 Mitigating Motion Blur in Neural Radiance Fields with Events and Frame
        116013, -- 2403.05086 UFORecon: Generalizable Sparse-View Surface Reconstruction from Arbitr
        116072, -- 2312.09866 PLGSLAM: Progressive Neural Scene Represenation with Local to Global B
        116095, -- 2404.02155 Alpha Invariance: On Inverse Scaling Between Distance and Volume Densi
        116146, -- 2402.17364 Learning Dynamic Tetrahedra for High-Quality Talking Head Synthesis
        116210, -- 2404.13024 BANF: Band-Limited Neural Fields for Levels of Detail Reconstruction
        116272, -- 2312.02434 FINER: Flexible Spectral-bias Tuning in Implicit NEural Representation
        116325, -- 2303.15368 2S-UDF: A Novel Two-stage UDF Learning Method for Robust Non-watertigh
        116350, -- 2401.12592 RGBD Objects in the Wild: Scaling Real-World 3D Object Learning from R
        116360, -- 2404.00931 GOV-NeSF: Generalizable Open-Vocabulary Neural Semantic Fields
        116363, -- 2404.10603 Enhancing 3D Fidelity of Text-to-3D using Cross-View Correspondences
        116409, -- 2403.18356 MonoHair: High-Fidelity Hair Modeling from a Monocular Video
        116415, -- 2312.05247 Dynamic LiDAR Re-simulation using Compositional Neural Fields
        116504, -- 2403.19473 Benchmarking Implicit Neural Representation and Geometric Rendering in
        116514, -- 2406.07111 NeRSP: Neural 3D Reconstruction for Reflective Objects with Sparse Pol
        116518, -- 2311.11016 SNI-SLAM: Semantic Neural Implicit SLAM
        116548, -- 2312.13328 NeLF-Pro: Neural Light Field Probes for Multi-Scale Novel View Synthes
        116566, -- 2312.02221 Slice3D: Multi-Slice Occlusion-Revealing Single View 3D Reconstruction
        116629, -- 2404.00098 Sparse Views Near Light: A Practical Paradigm for Uncalibrated Point-l
        116667, -- 2311.18695 Seg2Reg: Differentiable 2D Segmentation to 1D Regression Rendering for
        116695, -- 2312.03442 High-Quality Facial Geometry and Appearance Capture at Home
        116738, -- 2312.00778 MorpheuS: Neural Dynamic 360deg Surface Reconstruction from Monocular
        116752, -- 2405.00340 NC-SDF: Enhancing Indoor Scene Reconstruction Using Neural SDFs with V
        116770, -- 2405.19819 Gated Fields: Learning Scene Reconstruction from Gated Videos
        116786, -- 2312.05664 CoGS: Controllable Gaussian Splatting
        116793, -- 2405.19295 3D Neural Edge Reconstruction
        116828, -- 2403.14366 SurroundSDF: Implicit 3D Scene Understanding Based on Signed Distance
        116873, -- 2311.13187 NeISF: Neural Incident Stokes Field for Geometry and Material Estimati
        116886, -- 2306.15669 Detector-Free Structure from Motion
        116920, -- 2311.12754 SelfOcc: Self-Supervised Vision-Based 3D Occupancy Prediction
        116928, -- 2403.20002 Grounding and Enhancing Grid-based Models for Neural Fields
        116930, -- 2404.15707 ESR-NeRF: Emissive Source Reconstruction Using LDR Multi-view Images
        116947, -- 2404.01612 Spin-UP: Spin Light for Natural Light Uncalibrated Photometric Stereo
        116996, -- 2311.07044 L0-Sampler: An L0 Model Guided Volume Sampling for NeRF
        117027, -- 2404.14410 Guess The Unseen: Dynamic 3D Scene Reconstruction from Partial 2D Glim
        117051, -- 2402.09944 Loopy-SLAM: Dense Neural SLAM with Loop Closures
        117095, -- 2403.16885 CVT-xRF: Contrastive In-Voxel Transformer for 3D Consistent Radiance F
        117117, -- 2403.19517 XScale-NVS: Cross-Scale Novel View Synthesis with Hash Featurized Mani
        117127, -- 2403.18922 Lift3D: Zero-Shot Lifting of Any 2D Vision Model to 3D
        117139, -- 2403.04198 CN-RMA: Combined Network with Ray Marching Aggregation for 3D Indoor O
        117162, -- 2312.02480 Differentiable Point-based Inverse Rendering
        117191, -- 2312.06740 MonoNPHM: Dynamic Head Reconstruction from Monocular Videos
        117207, -- 2403.19314 Total-Decom: Decomposed 3D Scene Reconstruction with Minimal Interacti
        117243, -- 2404.04562 Diffusion Time-step Curriculum for One Image to 3D Generation
        117263, -- 2508.14891 GaussianArt: Unified Modeling of Geometry and Motion for Articulated O
        117268, -- 2502.14789 Structurally Disentangled Feature Fields Distillation for 3D Understan
        117271, -- 2601.12481 NeuralFur: Animal Fur Reconstruction from Multi-view Images
        117280, -- 2511.03950 Improving Multi-View Reconstruction via Texture-Guided Gaussian-Mesh J
        117282, -- 2411.09693 CropCraft: Complete Structural Characterization of Crop Plants from Im
        117295, -- 2509.04145 Hyper Diffusion Avatars: Dynamic Human Avatar Generation using Network
        117301, -- 2602.07860 Recovering 3D Shapes from Ultra-Fast Motion-Blurred Images
        117321, -- 2509.11087 SH-SAS: An Implicit Neural Representation for Complex Spherical-Harmon
        117347, -- 2512.22830 3D Scene Change Modeling with Consistent Multi-View Aggregation
        117357, -- 2506.13348 TextureSplat: Per-Primitive Texture Mapping for Reflective Gaussian Sp
        117361, -- 2601.05035 Patch-based Representation and Learning for Efficient Deformation Mode
        117373, -- 2511.19542 Proxy-Free Gaussian Splats Deformation with Splat-Based Surface Estima
        117392, -- 2606.30677 DANTE-W: Diffuse Albedo Neural Texturing in the Wild
        117394, -- 2606.20131 TriFlow: Generating Artist-Like 3D Mesh Topology via Nearest-Vertex Ve
        117446, -- 2606.31065 Diffusion-Based Material Regularization for Physics-Based Inverse Rend
        117541, -- 2604.07337 From Blobs to Spokes: High-Fidelity Surface Reconstruction via Oriente
        117546, -- 2607.03765 Sparse-View Surface Reconstruction using Gaussian Splatting through Hi
        117609, -- 2603.21695 RefracGS: Novel View Synthesis Through Refractive Water Surfaces with
        117617, -- 2604.01204 Neural Harmonic Textures for High-Quality Primitive Based Neural Recon
        117653, -- 2607.03771 City-Level 3D Surface Reconstruction with Viewpoint Orientation Partit
        117720, -- 2603.22851 UniQueR: Unified Query-based Feedforward 3D Reconstruction
        117892, -- 2607.09329 Dynamic Inverse Rendering for Enhanced Material-Lighting Decomposition
        118089, -- 2606.31172 HSDF-Lane: Height-Aligned Signed Distance Field with Semantic Lane Pri
        118267, -- 2512.17773 Pix2NPHM: Learning to Regress NPHM Reconstructions From a Single Image
        118314, -- 2606.03921 GARDEN: Gravity-Aligned Reconstruction of Disentangled ENvironments fr
        118324, -- 2607.08398 HoloTetSphere: Unified TetSphere Mesh Reconstruction for Physical Simu
        118703, -- 2607.02372 Learning Spectral and Polarimetric Clues for One-to-Multimodal Novel V
        119245, -- 2607.20660 Axolotl3D: a Unified Framework for Faithful 3D Shape Completion
        119464, -- 2608.05145 Objects as Audio-Visual Modal Sound Fields
        119707, -- 2312.13494 Visual Tomography: Physically Faithful Volumetric Models of Partially
        119713, -- 2302.03594 NICER-SLAM: Neural Implicit Scene Encoding for RGB SLAM
        119719, -- 2212.04492 Few-View Object Reconstruction with Unknown Categories and Camera Pose
        119745, -- 2403.19985 Stable Surface Regularization for Fast Few-Shot NeRF
        119759, -- 2405.12006 Depth Reconstruction with Neural Signed Distance Fields in Structured
        119761, -- 2401.09126 Objects With Lighting: A Real-World Dataset for Evaluating Reconstruct
        119766, -- 2310.17632 DeepShaRM: Multi-View Shape and Reflectance Map Recovery Under Unknown
        119780, -- 2406.08463 Self-Supervised Learning of Neural Implicit Feature Fields for Camera
        119782, -- 2211.14485 FastHuman: Reconstructing High-Quality Clothed Human in Minutes
        119784, -- 2402.06752 Oriented-grid Encoder for 3D Implicit Representations
        119804, -- 2312.05046 MuVieCAST: Multi-View Consistent Artistic Style Transfer
        119808, -- 2311.08159 DynamicSurf: Dynamic Neural RGB-D Surface Reconstruction With an Optim
        119812, -- 2403.14412 CombiNeRF: A Combination of Regularization Techniques for Few-Shot Neu
        119822, -- 2311.12174 LABELMAKER: Automatic Semantic Label Generation from RGB-D Trajectorie
        119823, -- 2308.04868 InstantAvatar: Efficient 3D Head Reconstruction via Surface Rendering
        119824, -- 2309.03008 Sparse 3D Reconstruction via Object-Centric Ray Sampling
        119829, -- 2311.12125 Mixing-Denoising Generalizable Occupancy Networks
        119838, -- 2506.07996 UA-Pose: Uncertainty-Aware 6D Object Pose Estimation and Online Object
        119870, -- 2411.11921 DeSiRe-GS: 4D Street Gaussians for Static-Dynamic Decomposition and Su
        119885, -- 2412.09680 PBR-NeRF: Inverse Rendering with Physics-Based Neural Fields
        120031, -- 2506.13110 GS-2DGS: Geometrically Supervised 2DGS for Reflective Object Reconstru
        120042, -- 2405.17811 Mani-GS: Gaussian Splatting Manipulation with Triangular Mesh
        120099, -- 2501.14277 Dense-SfM: Structure from Motion with Dense Consistent Matching
        120116, -- 2604.23010 GenAssets: Generating in-the-wild 3D Assets in Latent Space
        120306, -- 2503.13961 BG-Triangle: Bezier Gaussian Triangle for 3D Vectorization and Renderi
        120316, -- 2412.00905 Ref-GS: Directional Factorization for 2D Gaussian Splatting
        120390, -- 2411.18635 Radio Frequency Ray Tracing with Neural Object Representation for Enha
        120439, -- 2411.10189 NeISF++: Neural Incident Stokes Field for Polarized Inverse Rendering
        120499, -- 2503.19976 Thin-Shell-SfT: Fine-Grained Monocular Non-rigid 3D Surface Tracking w
        121684, -- 2602.24096 DiffusionHarmonizer: Bridging Neural Reconstruction and Photorealistic
        121910, -- 2605.29098 Seeing through boxes: Non-Line-of-Sight 3D Reconstruction from Radar S
        122285, -- 2609.35770 FurE: Efficient Instance-Specific 3D Fur Reconstruction without Animal
        122916, -- 2610.04722 NAMVIS: Next-Scale Autoregressive Multi-View Image Synthesis
        123190, -- 2610.03308 T3lescope: Arbitrary-Resolution High-Fidelity Generative Surface Recon
        123375, -- 2610.18846 WorldRecon: Generative Multi-View Mesh Reconstruction for Large-Scale
        124563, -- 2605.15010 3D Skew Normal Splatting
        125859, -- 2510.12174 UniGS: Unified Geometry-Aware Gaussian Splatting for Multimodal Render
        127020, -- 2610.11857 Pose-Free Feed-Forward 3D Inpainting via Learnable Mask Attention and
        127417, -- 2605.10360 DySurface: Consistent 4D Surface Reconstruction via Bridging Explicit
        127639, -- 2511.21098 Pygmalion Effect in Vision: Image-to-Clay Translation for Reflective G
        128802, -- 2605.29761 S2MDF: A Plug-And-Play Layer for Intersection-Free Multi-Object Signed
        129800, -- 2609.28684 M-plicits: Neural Implicit Surfaces via Nested Multiscale Residuals
        131327  -- 2305.17398 NeRO: Neural Geometry and BRDF Reconstruction of Reflective Objects fr
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
        11439, -- 2211.10440 Magic3D: High-Resolution Text-to-3D Content Creation
        11684, -- 2211.15977 One is All: Bridging the Gap Between Neural Radiance Fields Architectu
        11907, -- 2212.05231 NeuS2: Fast Learning of Neural Implicit Surfaces for Multi-view Recons
        12788, -- 2302.01330 SceneDreamer: Unbounded 3D Scene Generation from 2D Image Collections
        12808, -- 2302.01571 Robust Camera Pose Refinement for Multi-Resolution Hash Encoding
        13182, -- 2302.09311 Temporal Interpolation Is All You Need for Dynamic Neural Radiance Fie
        13630, -- 2303.05735 Hardware Acceleration of Neural Graphics
        14134, -- 2303.14536 SUDS: Scalable Urban Dynamic Scenes
        14218, -- 2303.15951 F$^{2}$-NeRF: Fast Neural Radiance Field Training with Free Camera Tra
        14545, -- 2304.04012 Progressive Volume Distillation with Active Learning for Efficient NeR
        14677, -- 2304.06706 Zip-NeRF: Anti-Aliased Grid-Based Neural Radiance Fields
        15234, -- 2305.03027 NeRSemble: Multi-view Radiance Field Reconstruction of Human Heads
        15348, -- 2305.04966 NerfAcc: Efficient Sampling Accelerates NeRFs
        16995, -- 2306.03092 Neuralangelo: High-Fidelity Neural Surface Reconstruction
        18255, -- 2307.07663 INVE: Interactive Neural Video Editing
        18373, -- 2307.09323 Efficient Region-Aware Neural Radiance Fields for High-Fidelity Talkin
        18458, -- 2307.10776 Urban Radiance Field Representation with Deformable Neural Mesh Primit
        18497, -- 2307.11335 Tri-MipRF: Tri-Mip Representation for Efficient Anti-Aliasing Neural R
        18603, -- 2307.13226 Strivec: Sparse Tri-Vector Radiance Fields
        19486, -- 2308.10122 HollowNeRF: Pruning Hashgrid-Based NeRFs with Trainable Collision Miti
        19879, -- 2308.14816 CLNeRF: Continual Learning Meets NeRF
        20623, -- 2309.10684 Locally Stylized Neural Radiance Fields
        20634, -- 2309.10815 PanopticNeRF-360: Panoramic 3D-to-2D Label Transfer in Urban Scenes
        20989, -- 2309.15848 SHACIRA: Scalable HAsh-grid Compression for Implicit Neural Representa
        22963, -- 2311.02542 VR-NeRF: High-Fidelity Virtualized Walkable Spaces
        23777, -- 2311.15439 Efficient Encoding of Graphics Primitives with Simplex-based Structure
        24484, -- 2312.04803 SuperNormal: Neural Surface Reconstruction via Multi-View Normal Integ
        24571, -- 2312.05984 Accurate Differential Operators for Hybrid Neural Fields
        25288, -- 2312.17241 Compact Neural Graphics Primitives with Learned Hash Probing
        25457, -- 2401.01970 FMGS: Foundation Model Embedded 3D Gaussian Splatting for Holistic 3D
        26000, -- 2401.10171 SHINOBI: Shape and Illumination using Neural Object Decomposition via
        29813, -- 2404.01543 Efficient 3D Implicit Head Avatar with Mesh-anchored Hash Table Blends
        30167, -- 2404.06780 Urban Architect: Steerable 3D Urban Scene Generation with Layout Prior
        30767, -- 2404.16510 Interactive3D: Create What You Want by Interactive 3D Generation
        31807, -- 2405.16868 RCDN: Towards Robust Camera-Insensitivity Collaborative Perception via
        37132, -- 2409.13648 V^3: Viewing Volumetric Videos on Mobiles via Streamable 2D Dynamic Ga
        43093, -- 2501.12637 DWTNeRF: Boosting Few-shot Neural Radiance Fields via Discrete Wavelet
        46011, -- 2503.10000 MetricGrids: Arbitrary Nonlinear Approximation with Elementary Metric
        48364, -- 2505.02005 Learning Heterogeneous Mixture of Scene Experts for Large-scale Neural
        52200, -- 2508.02831 GENIE: Gaussian Encoding for Neural Radiance Fields Interactive Editin
        57850, -- 2604.21984 Soft Anisotropic Diagrams for Differentiable Image Representation
        60874, -- 2602.10495 Characterizing and Optimizing the Spatial Kernel of Multi Resolution H
        64676, -- 2511.18384 NSTR: Neural Spectral Transport Representation for Space-Varying Frequ
        67039, -- 2510.08587 EGSTalker: Real-Time Audio-Driven Talking Head Generation with Efficie
        74708, -- 2502.09623 Weight Space Representation Learning on Diverse NeRF Architectures
        74735, -- 2502.08352 Sat-DN: Implicit Surface Reconstruction from Multi-View Satellite Imag
        75124, -- 2501.12255 HAC++: Towards 100X Compression of 3D Gaussian Splatting
        76334, -- 2407.08165 Explicit-NeRF-QA: A Quality Assessment Database for Explicit NeRF Mode
        85382, -- 2604.14706 NG-GS: NeRF-guided 3D Gaussian Splatting Segmentation
        88284, -- 2507.19141 DASH: 4D Hash Encoding with Self-Supervised Decomposition for Real-Tim
        92443, -- 2409.16921 Moner: Motion Correction in Undersampled Radial MRI with Unsupervised
        93740, -- 2601.10715 $\boldsymbol{\partial^\infty}$-Grid: A Neural Differential Equation So
        96343, -- 2509.20681 Efficient Construction of Implicit Surface Models from a Single Image
        97220, -- 2603.01850 Tiny-DroNeRF: Tiny Neural Radiance Fields Aboard Federated Learning-En
        101171, -- 2605.24774 Hermite-NGP: Gradient-Augmented Hash Encoding for Learning PDEs
        104878, -- 2603.05079 Beyond Positional Encoding: A 5D Spatio-Directional Hash Encoding
        105479, -- 2506.19742 NeRF-based CBCT Reconstruction needs Normalization and Initialization
        105527, -- external PD-INR: Prior-Driven Implicit Neural Representations for TOF-PET Recon
        107558, -- 2602.11705 TG-Field: Geometry-Aware Radiative Gaussian Fields for Tomographic Rec
        112448, -- 2403.14530 HAC: Hash-grid Assisted Context for 3D Gaussian Splatting Compression
        112455, -- 2409.14331 PISR: Polarimetric Neural Implicit Surface Reconstruction for Texturel
        112636, -- 2407.10482 NGP-RT: Fusing Multi-Level Hash Features with Lightweight Attention fo
        112637, -- external G2fR: Frequency Regularization in Grid-based Feature Encoding Neural R
        112714, -- 2409.05334 Lagrangian Hashing for Compressed Neural Field Representations
        112858, -- 2408.03193 Efficient NeRF Optimization - Not All Samples Remain Equally Hard
        112912, -- 2407.11962 Motion-Oriented Compositional Neural Radiance Fields for Monocular Dyn
        112960, -- 2410.19483 Content-Aware Radiance Fields: Aligning Model Complexity with Scene In
        113622, -- external Implicit Neural Models to Extract Heart Rate from Video
        113712, -- 2312.08744 GOEmbed: Gradient Origin Embeddings for Representation Agnostic 3D Fea
        114908, -- 2409.09387 Estimating Neural Orientation Distribution Fields on High Resolution D
        115455, -- 2404.14044 HashPoint: Accelerated Point Searching and Sampling for Neural Renderi
        115588, -- 2406.04101 How Far Can We Compress Instant-NGP-Based NeRF?
        116504, -- 2403.19473 Benchmarking Implicit Neural Representation and Geometric Rendering in
        116852, -- 2402.18771 NARUTO: Neural Active Reconstruction from Uncertain Target Observation
        117321, -- 2509.11087 SH-SAS: An Implicit Neural Representation for Complex Spherical-Harmon
        117356, -- 2511.06810 ConeGS: Error-Guided Densification Using Pixel Cones for Improved Reco
        117486, -- external CARA: Collision-Aware Resolution Adaptation for Multiresolution Hash E
        121469, -- external GH-NAF: Grid-Adaptive Hash-Level-Attended Neural Attenuation Fields fo
        124313, -- 2609.11894 3D Point Splatting for mmWave Radar Novel View Synthesis
        131008, -- 2606.00126 Bounding Global and Local Compression Error of Signal Parameterization
        132133  -- 2201.05989 Instant Neural Graphics Primitives with a Multiresolution Hash Encodin
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
        8462, -- 2203.15224 Panoptic NeRF: 3D-to-2D Label Transfer for Panoptic Urban Scene Segmen
        9023, -- 2205.07058 RTMV: A Ray-Traced Multi-View Synthetic Dataset for Novel View Synthes
        9218, -- 2205.13524 PREF: Phasorial Embedding Fields for Compact Neural Representations
        9298, -- 2205.15768 SAMURAI: Shape And Material from Unconstrained Real-world Arbitrary Im
        9481, -- 2206.07255 GRAM-HD: 3D-Consistent Image Generation at High Resolution with Genera
        9572, -- 2206.10885 KiloNeuS: A Versatile Neural Implicit Surface Representation for Real-
        9941, -- 2208.00277 MobileNeRF: Exploiting the Polygon Rasterization Pipeline for Efficien
        10499, -- 2210.00124 Implicit Neural Spatial Representations for Time-dependent PDEs
        10507, -- 2210.00379 NeRF: Neural Radiance Field in 3D Vision, A Comprehensive Review
        10512, -- 2210.00647 IntrinsicNeRF: Learning Intrinsic Neural Radiance Fields for Editable
        10742, -- 2210.06108 Reconstructing Personalized Semantic Facial NeRF Models From Monocular
        11036, -- 2210.13634 Vitruvio: 3D Building Meshes via Single Perspective Sketches
        11080, -- 2210.14831 Streaming Radiance Fields for 3D Video Synthesis
        11341, -- 2211.07600 Latent-NeRF for Shape-Guided Generation of 3D Shapes and Textures
        11466, -- 2211.11082 DynIBaR: Neural Dynamic Image-Based Rendering
        11513, -- 2211.12018 Level-S$^2$fM: Structure from Motion on Neural Level Set of Implicit S
        11517, -- 2211.12131 DiffDreamer: Towards Consistent Unsupervised Single-view Scene Extrapo
        11521, -- 2211.12254 SPIn-NeRF: Multiview Segmentation and Perceptual Inpainting with Neura
        11534, -- 2211.12499 Instant Volumetric Head Avatars
        11556, -- 2211.12853 BAD-NeRF: Bundle Adjusted Deblur Neural Radiance Fields
        11579, -- 2211.13226 ClimateNeRF: Extreme Weather Synthesis in Neural Radiance Field
        11701, -- 2211.16431 NeuralLift-360: Lifting An In-the-wild 2D Photo to A 3D Object with 36
        11732, -- 2212.00190 Mixed Neural Voxels for Fast Multi-view Video Synthesis
        11780, -- 2212.01331 Surface Normal Clustering for Implicit Representation of Manhattan Sce
        11789, -- 2212.01602 StegaNeRF: Embedding Invisible Information within Neural Radiance Fiel
        11837, -- 2212.03267 NeRDi: Single-View NeRF Synthesis with Language-Guided Diffusion as Ge
        11969, -- 2212.07378 3DHumanGAN: 3D-Aware Human Image Generation with 3D Pose Mapping
        11971, -- 2212.07388 NoPe-NeRF: Optimising Neural Radiance Field with No Pose Prior
        12004, -- 2212.08057 Real-Time Neural Light Field on Mobile Devices
        12007, -- 2212.08067 VolRecon: Volume Rendering of Signed Ray Distance Functions for Genera
        12096, -- 2212.09802 Panoptic Lifting for 3D Scene Understanding with Neural Fields
        12207, -- 2212.12324 Shakes on a Plane: Unsupervised Depth Estimation from Unstabilized Pho
        12258, -- 2212.14593 NIRVANA: Neural Implicit Representations of Videos with Adaptive Netwo
        12267, -- 2301.00157 Ponder: Point Cloud Pre-training via Neural Rendering
        12319, -- 2301.02238 HyperReel: High-Fidelity 6-DoF Video with Ray-Conditioned Sampling
        12320, -- 2301.02239 Robust Dynamic Radiance Fields
        12378, -- 2301.04695 Learning Continuous Mesh Representation with Spherical Implicit Surfac
        12420, -- 2301.06782 A Large-Scale Outdoor Multi-modal Dataset and Benchmark for Novel View
        12435, -- 2301.07525 OmniObject3D: Large-Vocabulary 3D Object Dataset for Realistic Percept
        12456, -- 2301.08556 NeRF in the Palm of Your Hand: Corrective Augmentation for Robotics vi
        12490, -- 2301.09632 HexPlane: A Fast Representation for Dynamic Scenes
        12535, -- 2301.10941 GeCoNeRF: Few-shot Neural Radiance Fields via Geometric Consistency
        12552, -- 2301.11280 Text-To-4D Dynamic Scene Generation
        12821, -- 2302.01838 vMAP: Vectorised Object Mapping for Neural Field SLAM
        12957, -- 2302.04264 Nerfstudio: A Modular Framework for Neural Radiance Field Development
        13155, -- 2302.08509 3D-aware Conditional Image Synthesis
        13218, -- 2302.10351 Variational Autoencoding Neural Operators
        13228, -- 2302.10663 RealFusion: 360° Reconstruction of Any Object from a Single Image
        13287, -- 2302.12249 MERF: Memory-Efficient Radiance Fields for Real-time View Synthesis in
        13366, -- 2302.14340 HelixSurf: A Robust and Efficient Neural Implicit Surface Learning of
        13476, -- 2303.02091 Delicate Textured Mesh Recovery from NeRF via Adaptive Surface Refinem
        13487, -- 2303.02375 NeuDA: Neural Deformable Anchor for High-Fidelity Implicit Surface Rec
        13581, -- 2303.04869 CROSSFIRE: Camera Relocalization On Self-Supervised Features from an I
        13609, -- 2303.05312 3D Video Loops from Asynchronous Input
        13637, -- 2303.05937 Structural Multiplane Image: Bridging Neural View Synthesis and 3D Rec
        13698, -- 2303.06919 NeRFLiX: High-Quality Neural View Synthesis by Learning a Degradation-
        13789, -- 2303.08717 Re-ReND: Real-time Rendering of NeRFs across Devices
        13815, -- 2303.09152 Learning a Room with the Occ-SDF Hybrid: Signed Distance Function Ming
        13830, -- 2303.09431 NeRFMeshing: Distilling Neural Radiance Fields into Geometrically-Accu
        13840, -- 2303.09553 LERF: Language Embedded Radiance Fields
        13870, -- 2303.10087 Neural Refinement for Absolute Pose Regression with Feature Synthesis
        13892, -- 2303.10559 Deep Learning for Camera Calibration and Beyond: A Survey
        13896, -- 2303.10598 StyleRF: Zero-shot 3D Style Transfer of Neural Radiance Fields
        13900, -- 2303.10735 SKED: Sketch-guided Text-based 3D Editing
        13963, -- 2303.11717 A Complete Survey on Generative AI (AIGC): Is ChatGPT from GPT-4 to GP
        13978, -- 2303.11963 NEMTO: Neural Environment Matting for Novel View and Relighting Synthe
        14029, -- 2303.12791 SHERF: Generalizable Human NeRF from a Single Image
        14034, -- 2303.12965 Efficient Meshy Neural Fields for Animatable Human Avatars
        14037, -- 2303.13022 ENVIDR: Implicit Differentiable Renderer with Neural Environment Light
        14075, -- 2303.13612 NOPE: Novel Object Pose Estimation from a Single Image
        14082, -- 2303.13791 Progressively Optimized Local Radiance Fields for Robust View Synthesi
        14088, -- 2303.13873 Fantasia3D: Disentangling Geometry and Appearance for High-quality Tex
        14093, -- 2303.13953 AssetField: Assets Mining and Reconfiguration in Ground Feature Plane
        14103, -- 2303.14158 BundleSDF: Neural 6-DoF Tracking and 3D Reconstruction of Unknown Obje
        14104, -- 2303.14167 UrbanGIRAFFE: Representing Urban Scenes as Compositional Generative Ne
        14107, -- 2303.14184 Make-It-3D: High-Fidelity 3D Creation from A Single Image with Diffusi
        14183, -- 2303.15387 Generalizable Neural Voxels for Fast Human Radiance Fields
        14228, -- 2303.16184 VMesh: Hybrid Volume-Mesh Representation for Efficient View Synthesis
        14235, -- 2303.16242 CuNeRF: Cube-Based Neural Radiance Field for Zero-Shot Medical Image A
        14287, -- 2303.17147 NeILF++: Inter-Reflectable Light Fields for Geometry and Material Esti
        14321, -- 2303.17606 AvatarCraft: Transforming Text into Neural Human Avatars with Paramete
        14331, -- 2303.17806 Neural Microfacet Fields for Inverse Rendering
        14384, -- 2304.00782 NeMF: Inverse Volume Rendering with Neural Microflake Field
        14472, -- 2304.02330 SMPConv: Self-moving Point Representations for Continuous Convolution
        14481, -- 2304.02602 Generative Novel View Synthesis with 3D-Aware Diffusion Models
        14483, -- 2304.02626 Dynamic Point Fields
        14557, -- 2304.04278 Point-SLAM: Dense Neural Point Cloud-based SLAM
        14564, -- 2304.04395 Instance Neural Radiance Field
        14633, -- 2304.05669 Factorized Inverse Path Tracing for Efficient and Accurate Material-Li
        14660, -- 2304.06287 NeRFVS: Neural Radiance Fields for Free View Synthesis via Geometry Sc
        14759, -- 2304.08757 NeAI: A Pre-convoluted Representation for Plug-and-Play Neural Ambient
        14770, -- 2304.08971 SurfelNeRF: Neural Surfel Radiance Fields for Online Photorealistic Re
        14777, -- 2304.09121 Fast Neural Scene Flow
        14801, -- 2304.09677 Reference-guided Controllable Inpainting of Neural Radiance Fields
        14822, -- 2304.09987 Tetra-NeRF: Representing Neural Radiance Fields Using Tetrahedra
        14826, -- 2304.10075 Multiscale Representation for Real-Time Anti-Aliasing Neural Rendering
        14848, -- 2304.10532 Nerfbusters: Removing Ghostly Artifacts from Casually Captured NeRFs
        14919, -- 2304.12294 Explicit Correspondence Matching for Generalizable Neural Radiance Fie
        14939, -- 2304.12670 Patch-based 3D Natural Scene Generation from a Single Example
        14978, -- 2304.13445 Neural-PBIR Reconstruction of Shape, Material, and Illumination
        15096, -- 2305.00787 GeneFace++: Generalized and Stable Real-Time Audio-Driven 3D Talking F
        15102, -- 2305.00942 StyleAvatar: Real-time Photo-realistic Portrait Avatar from a Single V
        15152, -- 2305.01643 Neural LiDAR Fields for Novel View Synthesis
        15215, -- 2305.02678 Real-Time Neural Appearance Models
        15306, -- 2305.04268 Multi-Space Neural Radiance Fields
        15335, -- 2305.04789 AvatarReX: Real-time Expressive Full-body Avatars
        15408, -- 2305.06118 NeRF2: Neural Radio-Frequency Radiance Fields
        15409, -- 2305.06131 Generative AI meets 3D: A Survey on Text-to-3D in AIGC Era
        15432, -- 2305.06356 HumanRF: High-Fidelity Neural Radiance Fields for Humans in Motion
        15494, -- 2305.07514 BlendFields: Few-Shot Example-Driven Facial Modeling
        15572, -- 2305.08810 AutoRecon: Automated 3D Object Discovery and Reconstruction
        15580, -- 2305.08851 MV-Map: Offboard HD-Map Generation with Multi-view Consistency
        15628, -- 2305.09761 NerfBridge: Bringing Real-time, Online Neural Radiance Field Training
        15859, -- 2305.12529 DreamWaltz: Make a Scene with Complex 3D Animatable Avatars
        16062, -- 2305.14312 Text-guided 3D Human Generation from 2D Collections
        16308, -- 2305.16213 ProlificDreamer: High-Fidelity and Diverse Text-to-3D Generation with
        16336, -- 2305.16411 ZeroAvatar: Zero-shot 3D Avatar Generation from a Single Image
        16569, -- 2305.18766 HiFA: High-fidelity Text-to-3D Generation with Advanced Diffusion Guid
        16691, -- 2305.20082 Control4D: Efficient 4D Portrait Editing with Text
        16845, -- 2306.01344 Adjustable Visual Appearance for Generalizable Novel View Synthesis
        16966, -- 2306.02851 Scene as Occupancy
        16979, -- 2306.03000 BeyondPixels: A Comprehensive Review of the Evolution of Neural Radian
        16985, -- 2306.03038 HeadSculpt: Crafting 3D Head Avatars with Text
        17180, -- 2306.05407 SNAP: Self-Supervised Neural Maps for Visual Positioning and Semantic
        17181, -- 2306.05410 LU-NeRF: Scene and Pose Estimation by Synchronizing Local Unposed NeRF
        17185, -- 2306.05422 Tracking Everything Everywhere All at Once
        17207, -- 2306.05668 RePaint-NeRF: NeRF Editting via Semantic Masks and Diffusion Models
        17230, -- 2306.06044 GANeRF: Leveraging Discriminators to Optimize Neural Radiance Fields
        17314, -- 2306.07266 Operator Learning with Neural Fields: Tackling PDEs on General Geometr
        17326, -- 2306.07349 ATT3D: Amortized Text-to-3D Object Synthesis
        17465, -- 2306.09109 NAVI: Category-Agnostic Image Collections with High-Quality 3D Shape a
        17488, -- 2306.09322 Neural Relighting with Subsurface Scattering by Learning the Radiance
        17500, -- 2306.09348 Seeing the World through Your Eyes
        17501, -- 2306.09349 UrbanIR: Large-Scale Urban Scene Inverse Rendering from a Single Video
        17574, -- 2306.10533 Point-Cloud Completion with Pretrained Text-to-image Diffusion Models
        17644, -- 2306.11920 NILUT: Conditional Neural Implicit 3D Lookup Tables for Image Enhancem
        17665, -- 2306.12422 DreamTime: An Improved Optimization Strategy for Diffusion-Guided 3D G
        17711, -- 2306.13455 DreamEditor: Text-Driven 3D Scene Editing with Neural Fields
        17798, -- 2306.15242 SPDER: Semiperiodic Damping-Enabled Object Representation
        17924, -- 2306.17843 Magic123: One Image to High-Quality 3D Object Generation Using Both 2D
        18146, -- 2307.05000 Neural Point-based Volumetric Avatar: Surface-guided Neural Points for
        18307, -- 2307.08351 Neural Modulation Fields for Conditional Cone Beam Neural Tomography
        18420, -- 2307.10173 DNA-Rendering: A Diverse Neural Actor Repository for High-Fidelity Hum
        18424, -- 2307.10235 Towards Viewpoint-Invariant Visual Recognition via Adversarial Trainin
        18449, -- 2307.10664 Lighting up NeRF via Unsupervised Decomposition and Enhancement
        18638, -- 2307.13908 Points-to-3D: Bridging the Gap between Sparse Points and Shape-Control
        18717, -- 2307.15058 MARS: An Instance-aware, Modular and Realistic Simulator for Autonomou
        18721, -- 2307.15131 Seal-3D: Interactive Pixel-Level Editing for Neural Radiance Fields
        18732, -- 2307.15333 Dynamic PlenOctree for Adaptive Sampling Refinement in Explicit NeRF
        18876, -- 2308.01477 HANDAL: A Dataset of Real-World Manipulable Object Categories with Pos
        18901, -- 2308.01898 UniSim: A Neural Closed-Loop Sensor Simulator
        19011, -- 2308.03757 3D Motion Magnification: Visualizing Subtle Motions with Time Varying
        19030, -- 2308.04079 3D Gaussian Splatting for Real-Time Radiance Field Rendering
        19062, -- 2308.04622 Rendering Humans from Object-Occluded Monocular Videos
        19080, -- 2308.04826 WaveNeRF: Wavelet-based Generalizable Neural Radiance Fields
        19106, -- 2308.05371 Flexible Isosurface Extraction for Gradient-Based Mesh Optimization
        19221, -- 2308.07032 S3IM: Stochastic Structural SIMilarity and Its Unreasonable Effectiven
        19247, -- 2308.07391 PARIS: Part-level Reconstruction and Motion Analysis for Articulated O
        19279, -- 2308.07868 ObjectSDF++: Improved Object-Compositional Neural Implicit Surfaces
        19288, -- 2308.07926 CoDeF: Content Deformation Fields for Temporally Consistent Video Proc
        19290, -- 2308.07931 Distilled Feature Fields Enable Few-Shot Language-Guided Manipulation
        19315, -- 2308.08258 SceNeRFlow: Time-Consistent Reconstruction of General Dynamic Scenes
        19334, -- 2308.08545 TeCH: Text-guided Reconstruction of Lifelike Clothed Humans
        19361, -- 2308.08947 Watch Your Steps: Local Image and Scene Editing by Text Instructions
        19366, -- 2308.09098 ImGeoNet: Image-induced Geometry-aware Voxel Representation for Multi-
        19402, -- 2308.09386 DReg-NeRF: Deep Registration for Neural Radiance Fields
        19437, -- 2308.09713 Dynamic 3D Gaussians: Tracking by Persistent Dynamic View Synthesis
        19520, -- 2308.10337 Strata-NeRF : Neural Radiance Fields for Stratified Scenes
        19584, -- 2308.11015 Spectral Graphormer: Spectral Graph-based Transformer for Egocentric T
        19585, -- 2308.11025 Coordinate Quantized Neural Implicit Representations for Multi-view Re
        19597, -- 2308.11130 Efficient View Synthesis with Neural Radiance Distribution Field
        19605, -- 2308.11198 Novel-view Synthesis and Pose Estimation for Hand-Object Interaction f
        19622, -- 2308.11417 ScanNet++: A High-Fidelity Dataset of 3D Indoor Scenes
        19625, -- 2308.11441 Learning a More Continuous Zero Level Set in Unsigned Distance Fields
        19658, -- 2308.11793 Enhancing NeRF akin to Enhancing LLMs: Generalizable NeRF Transformer
        19676, -- 2308.11974 Blending-NeRF: Text-Driven Localized Editing in Neural Radiance Fields
        19757, -- 2308.12967 NeO 360: Neural Fields for Sparse View Synthesis of Outdoor Scenes
        19770, -- 2308.13175 GridPull: Towards Scalability in Learning Implicit Representations fro
        19774, -- 2308.13223 EfficientDreamer: High-Fidelity and Robust 3D Creation via Orthogonal-
        19831, -- 2308.14078 Sparse3D: Distilling Multiview-Consistent Diffusion for Object Reconst
        19859, -- 2308.14383 Multi-Modal Neural Radiance Field for Monocular Dense SLAM with a Ligh
        19893, -- 2308.15049 Pose-Free Neural Radiance Fields via Implicit Pose Regularization
        19915, -- 2308.15461 Canonical Factors for Hybrid Neural Fields
        19922, -- 2308.15536 DebSDF: Delving into the Details and Bias of Neural Indoor Scene Recon
        19965, -- 2308.16512 MVDream: Multi-view Diffusion for 3D Generation
        20133, -- 2309.02436 GO-SLAM: Global Optimization for Consistent 3D Instant Reconstruction
        20159, -- 2309.03160 ResFields: Residual Neural Fields for Spatiotemporal Signals
        20163, -- 2309.03185 Bayes' Rays: Uncertainty Quantification for Neural Radiance Fields
        20192, -- 2309.03811 Panoramas from Photons
        20232, -- 2309.04581 Dynamic Mesh-Aware Radiance Fields
        20255, -- 2309.04917 Editing 3D Scenes via Text Prompts without Retraining
        20334, -- 2309.06441 Learning Disentangled Avatars with Hybrid 3D Representations
        20358, -- 2309.06802 Dynamic NeRFs for Soccer Scenes
        20419, -- 2309.07749 OmnimatteRF: Robust Omnimatte with 3D Background Modeling
        20437, -- 2309.07921 OpenIllumination: A Multi-Illumination Dataset for Inverse Rendering E
        20441, -- 2309.07970 Language Embedded Radiance Fields for Zero-Shot Task-Oriented Grasping
        20480, -- 2309.08523 Breathing New Life into 3D Assets with Generative Repainting
        20490, -- 2309.08596 Robust e-NeRF: NeRF from Sparse & Noisy Events under Non-Uniform Motio
        20522, -- 2309.08957 ExBluRF: Efficient Radiance Fields for Extreme Motion Blurred Images
        20546, -- 2309.09502 RenderOcc: Vision-Centric 3D Occupancy Prediction with 2D Rendering Su
        20601, -- 2309.10336 Anti-Aliased Neural Implicit Surfaces with Encoding Level of Detail
        20674, -- 2309.11258 TwinTex: Geometry-aware Texture Generation for Abstracted 3D Architect
        20803, -- 2309.13039 NeRRF: 3D Reconstruction and View Synthesis for Transparent and Specul
        20811, -- 2309.13101 Deformable 3D Gaussians for High-Fidelity Monocular Dynamic Scene Reco
        20876, -- 2309.14022 Hashing Neural Video Decomposition with Multiplicative Residuals in Sp
        20892, -- 2309.14291 Tiled Multiplane Images for Practical 3D Photography
        20931, -- 2309.14872 Directional Texture Editing for 3D Models
        20964, -- 2309.15426 NeuRBF: A Neural Fields Representation with Adaptive Radial Basis Func
        21037, -- 2309.16585 Text-to-3D using Gaussian Splatting
        21044, -- 2309.16653 DreamGaussian: Generative Gaussian Splatting for Efficient 3D Content
        21083, -- 2309.17182 RECOMBINER: Robust and Enhanced Compression with Bayesian Implicit Neu
        21090, -- 2309.17261 Consistent123: One Image to Highly Consistent 3D Asset Using Case-Awar
        21252, -- 2310.01406 HumanNorm: Learning Normal Diffusion Model for High-quality and Realis
        21304, -- 2310.01830 AI-Generated Images as Data Source: The Dawn of Synthetic Era
        21368, -- 2310.02596 SweetDreamer: Aligning Geometric Priors in 2D Diffusion for Consistent
        21377, -- 2310.02712 ED-NeRF: Efficient Text-Guided Editing of 3D Scene with Latent Space N
        21464, -- 2310.03704 Pose-Free Generalizable Rendering Transformer
        21609, -- 2310.05375 IPDreamer: Appearance-Controllable 3D Object Generation with Complex I
        21622, -- 2310.05483 HarmonicNeRF: Geometry-Informed Synthetic View Augmentation for 3D Sce
        21628, -- 2310.05524 Parameterization-driven Neural Surface Reconstruction for Object-orien
        21726, -- 2310.06744 HiFi-123: Towards High-fidelity One Image to 3D Content Generation
        21752, -- 2310.06984 Leveraging Neural Radiance Fields for Uncertainty-Aware Visual Localiz
        21794, -- 2310.07449 PoRF: Pose Residual Field for Accurate Neural Surface Reconstruction
        21849, -- 2310.08092 Consistent123: Improve Consistency for One Image to 3D Object Synthesi
        21895, -- 2310.08528 4D Gaussian Splatting for Real-Time Dynamic Scene Rendering
        21896, -- 2310.08529 GaussianDreamer: Fast Generation from Text to 3D Gaussians by Bridging
        21912, -- 2310.08585 Im4D: High-Fidelity and Real-Time Novel View Synthesis for Dynamic Sce
        21913, -- 2310.08586 PonderV2: Pave the Way for 3D Foundation Model with A Universal Pre-tr
        21972, -- 2310.09458 PaintHuman: Towards High-fidelity Text-to-3D Human Texturing via Denoi
        22007, -- 2310.09965 ProteusNeRF: Fast Lightweight NeRF Editing using 3D-Aware Image Contex
        22065, -- 2310.10642 Real-time Photorealistic Dynamic Scene Representation and Rendering wi
        22066, -- 2310.10644 TOSS:High-quality Text-guided Novel View Synthesis from a Single Image
        22123, -- 2310.11448 4K4D: Real-Time 4D View Synthesis at 4K Resolution
        22269, -- 2310.13263 UE4-NeRF:Neural Radiance Field for Real-Time Rendering of Large-Scale
        22309, -- 2310.13772 TexFusion: Synthesizing 3D Textures with Text-Guided Image Diffusion M
        22356, -- 2310.14487 VQ-NeRF: Vector Quantization Enhances Implicit Neural Representations
        22566, -- 2310.16818 DreamCraft3D: Hierarchical 3D Generation with Bootstrapped Diffusion P
        22569, -- 2310.16831 PERF: Panoramic Neural Radiance Field from a Single Panorama
        22570, -- 2310.16832 LightSpeed: Light and Fast Neural Light Fields on Mobile Devices
        22586, -- 2310.17075 HyperFields: Towards Zero-Shot Generation of NeRFs from Text
        22643, -- 2310.17880 Reconstructive Latent-Space Neural Radiance Fields for Efficient 3D Sc
        22653, -- 2310.17994 ZeroNVS: Zero-Shot 360-Degree View Synthesis from a Single Image
        22671, -- 2310.18308 Gen2Sim: Scaling up Robot Learning in Simulation with Generative Model
        22747, -- 2310.19415 Text-to-3D with Classifier Score Distillation
        22760, -- 2310.19629 RayDF: Neural Ray-surface Distance Fields with Multi-view Consistency
        22826, -- 2310.20710 FPO++: Efficient Encoding and Rendering of Dynamic Neural Radiance Fie
        22946, -- 2311.02077 EmerNeRF: Emergent Spatial-Temporal Scene Decomposition via Self-Super
        23073, -- 2311.04400 LRM: Large Reconstruction Model for Single Image to 3D
        23138, -- 2311.05607 Real-Time Neural Rasterization for Large Scenes
        23171, -- 2311.06214 Instant3D: Fast Text-to-3D with Sparse-View Generation and Large Recon
        23321, -- 2311.08403 Instant3D: Instant Text-to-3D Generation
        23330, -- 2311.08581 Drivable 3D Gaussian Avatars
        23390, -- 2311.09217 DMV3D: Denoising Multi-View Diffusion using 3D Large Reconstruction Mo
        23449, -- 2311.09806 EvaSurf: Efficient View-Aware Implicit Textured Surface Reconstruction
        23464, -- 2311.10091 Adaptive Shells for Efficient Neural Radiance Field Rendering
        23468, -- 2311.10123 MetaDreamer: Efficient Text-to-3D Creation With Disentangling Geometry
        23542, -- 2311.11666 OmniSeg3D: Omniversal 3D Segmentation via Hierarchical Contrastive Lea
        23569, -- 2311.12024 PF-LRM: Pose-Free Large Reconstruction Model for Joint Pose and Shape
        23582, -- 2311.12198 PhysGaussian: Physics-Integrated 3D Gaussians for Generative Dynamics
        23606, -- 2311.12490 Hyb-NeRF: A Multiresolution Hybrid Encoding for Neural Radiance Fields
        23616, -- 2311.12775 SuGaR: Surface-Aligned Gaussian Splatting for Efficient 3D Mesh Recons
        23658, -- 2311.13297 Retargeting Visual Data with Deformation Fields
        23662, -- 2311.13384 LucidDreamer: Domain-free Generation of 3D Gaussian Splatting Scenes
        23664, -- 2311.13398 Depth-Regularized Optimization for 3D Gaussian Splatting in Few-Shot I
        23686, -- 2311.13681 Compact 3D Gaussian Representation for Radiance Field
        23722, -- 2311.14521 GaussianEditor: Swift and Controllable 3D Editing with Gaussian Splatt
        23726, -- 2311.14603 Animate124: Animating One Image to 4D Dynamic Scene
        23749, -- 2311.14993 Coordinate-Aware Modulation for Neural Fields
        23767, -- 2311.15260 NeuRAD: Neural Rendering for Autonomous Driving
        23769, -- 2311.15291 Obj-NeRF: Extract Object NeRFs from Multi-view Images
        23810, -- 2311.15855 SiTH: Single-view Textured Human Reconstruction with Image-Conditioned
        23821, -- 2311.15980 Direct2.5: Diverse Text-to-3D Generation via Multi-view 2.5D Diffusion
        23824, -- 2311.16037 GaussianEditor: Editing 3D Gaussians Delicately with Text Instructions
        23825, -- 2311.16043 Relightable 3D Gaussians: Realistic Point Cloud Relighting with BRDF D
        23855, -- 2311.16473 GS-IR: 3D Gaussian Splatting for Inverse Rendering
        23857, -- 2311.16493 Mip-Splatting: Alias-free 3D Gaussian Splatting
        23860, -- 2311.16499 InceptionHuman: Controllable Prompt-to-NeRF for Photorealistic 3D Huma
        23885, -- 2311.16854 A Unified Approach for Text- and Image-guided 4D Scene Generation
        23890, -- 2311.16918 RichDreamer: A Generalizable Normal-Depth Diffusion Model for Detail R
        23918, -- 2311.17094 In Search of a Data Transformation That Accelerates Neural Field Train
        23922, -- 2311.17113 Human Gaussian Splatting: Real-time Rendering of Animatable Avatars
        23924, -- 2311.17123 ConTex-Human: Free-View Rendering of Human from a Single Image with Te
        23936, -- 2311.17245 LightGaussian: Unbounded 3D Gaussian Compression with 15x Reduction an
        23938, -- 2311.17261 SceneTex: High-Quality Texture Synthesis for Indoor Scenes via Diffusi
        23959, -- 2311.17590 SyncTalk: The Devil is in the Synchronization for Talking Head Synthes
        23964, -- 2311.17643 Neural Fields with Thermal Activations for Arbitrary-Scale Super-Resol
        23980, -- 2311.17874 FisherRF: Active View Selection and Uncertainty Quantification for Rad
        23984, -- 2311.17910 HUGS: Human Gaussian Splats
        23986, -- 2311.17917 AvatarStudio: High-fidelity and Animatable 3D Avatar Creation from Tex
        23998, -- 2311.17971 GeoDream: Disentangling 2D and Geometric Priors for High-Fidelity and
        24001, -- 2311.17984 4D-fy: Text-to-4D Generation Using Hybrid Score Distillation Sampling
        24008, -- 2311.18159 CompGS: Smaller and Faster Gaussian Splatting with Vector Quantization
        24024, -- 2311.18482 Language Embedded 3D Gaussians for Open-Vocabulary Scene Understanding
        24033, -- 2311.18561 Periodic Vibration Gaussian: Dynamic Urban Scene Reconstruction and Re
        24075, -- 2312.00085 X-Dreamer: Creating High-quality 3D Content by Bridging the Domain Gap
        24077, -- 2312.00093 GraphDreamer: Compositional 3D Scene Synthesis from Scene Graphs
        24079, -- 2312.00109 Scaffold-GS: Structured 3D Gaussians for View-Adaptive Rendering
        24088, -- 2312.00206 SparseGS: Real-Time 360° Sparse View Synthesis using Gaussian Splattin
        24093, -- 2312.00252 PyNeRF: Pyramidal Neural Radiance Fields
        24113, -- 2312.00451 FSGS: Real-Time Few-shot View Synthesis using Gaussian Splatting
        24120, -- 2312.00583 DeformGS: Scene Flow in Highly Deformable Scenes for Deformable Object
        24121, -- 2312.00588 LucidDreaming: Controllable Object-Centric 3D Generation
        24133, -- 2312.00739 Adversarial Score Distillation: When score distillation meets GAN
        24152, -- 2312.00860 Segment Any 3D Gaussians
        24170, -- 2312.01129 ControlDreamer: Blending Geometry and Style in Text-to-3D
        24183, -- 2312.01407 VideoRF: Rendering Dynamic Radiance Fields as 2D Feature Video Streams
        24189, -- 2312.01531 SANeRF-HQ: Segment Anything for NeRF in High Quality
        24197, -- 2312.01663 Customize your NeRF: Adaptive Source Driven 3D Scene Editing via Local
        24223, -- 2312.02069 GaussianAvatars: Photorealistic Head Avatars with Rigged 3D Gaussians
        24224, -- 2312.02087 VideoSwap: Customized Video Subject Swapping with Interactive Semantic
        24241, -- 2312.02155 GPS-Gaussian: Generalizable Pixel-wise 3D Gaussian Splatting for Real-
        24244, -- 2312.02189 StableDreamer: Taming Noisy Score Distillation Sampling for Text-to-3D
        24250, -- 2312.02214 FlashAvatar: High-fidelity Head Avatar with Efficient Gaussian Embeddi
        24265, -- 2312.02350 Instant Uncertainty Calibration of NeRFs Using a Meta-Calibrator
        24282, -- 2312.02568 Prompt2NeRF-PIL: Fast NeRF Generation via Pretrained Implicit Latent
        24302, -- 2312.02902 HeadGaS: Real-Time Animatable Head Avatars via 3D Gaussian Splatting
        24309, -- 2312.02936 Drag-A-Video: Non-rigid Video Editing with Point-based Interaction
        24311, -- 2312.02963 MVHumanNet: A Large-scale Dataset of Multi-view Daily Dressing Human C
        24315, -- 2312.02973 GauHuman: Articulated Gaussian Splatting from Monocular Human Videos
        24336, -- 2312.03160 HybridNeRF: Efficient Neural Rendering via Adaptive Volumetric Surface
        24337, -- 2312.03203 Feature 3DGS: Supercharging 3D Gaussian Splatting to Enable Distilled
        24347, -- 2312.03431 Gaussian-Flow: 4D Reconstruction with Dynamic 3D Gaussian Particle
        24349, -- 2312.03461 HiFi4G: High-Fidelity Human Performance Rendering via Compact Gaussian
        24443, -- 2312.04501 Graph Metanetworks for Processing Diverse Neural Architectures
        24451, -- 2312.04533 Dream2Real: Zero-Shot 3D Object Rearrangement with Vision-Language Mod
        24454, -- 2312.04543 HyperDreamer: Hyper-Realistic 3D Content Generation and Editing from a
        24458, -- 2312.04551 Free3D: Consistent Novel View Synthesis without 3D Representation
        24465, -- 2312.04564 EAGLES: Efficient Accelerated 3D Gaussians with Lightweight EncodingS
        24482, -- 2312.04784 Reality's Canvas, Language's Brush: Crafting 3D Avatars from Monocular
        24497, -- 2312.04963 Text-to-3D Generation with Bidirectional Diffusion using both 2D and 3
        24504, -- 2312.05161 TriHuman : A Real-time and Controllable Tri-plane Representation for D
        24510, -- 2312.05210 IntrinsicAvatar: Physically Based Inverse Rendering of Dynamic Humans
        24558, -- 2312.05748 IL-NeRF: Incremental Learning for Neural Radiance Fields with Camera P
        24567, -- 2312.05941 ASH: Animatable Gaussian Splats for Efficient and Photoreal Human Rend
        24602, -- 2312.06575 EasyVolcap: Accelerating Neural Volumetric Video Research
        24615, -- 2312.06654 LightSim: Neural Lighting Simulation for Urban Scenes
        24617, -- 2312.06657 Learning Naturally Aggregated Appearance for Efficient 3D Editing
        24619, -- 2312.06661 UpFusion: Novel View Diffusion from Unposed Sparse View Observations
        24639, -- 2312.06741 Gaussian Splatting SLAM
        24673, -- 2312.07315 NVS-Adapter: Plug-and-Play Novel View Synthesis from a Single Image
        24690, -- 2312.07504 COLMAP-Free 3D Gaussian Splatting
        24698, -- 2312.07539 HeadArtist: Text-conditioned 3D Head Generation with Self Score Distil
        24700, -- 2312.07541 SMERF: Streamable Memory Efficient Radiance Fields for Real-Time Large
        24727, -- 2312.08136 ProNeRF: Learning Efficient Projection-Aware Ray Sampling for Fine-Gra
        24733, -- 2312.08338 Global Latent Neural Rendering
        24734, -- 2312.08344 FoundationPose: Unified 6D Pose Estimation and Tracking of Novel Objec
        24740, -- 2312.08372 SAM-guided Graph Cut for 3D Instance Segmentation
        24748, -- 2312.08568 NViST: In the Wild New View Synthesis from a Single Image with Transfo
        24774, -- 2312.08885 SceneWiz3D: Towards Text-guided 3D Scene Composition
        24776, -- 2312.08889 SEEAvatar: Photorealistic Text-to-3D Avatar Generation with Constraine
        24797, -- 2312.09147 Triplane Meets Gaussian Splatting: Fast and Generalizable Single-View
        24803, -- 2312.09222 Mosaic-SDF for 3D Generative Models
        24804, -- 2312.09228 3DGS-Avatar: Animatable Avatars via Deformable 3D Gaussian Splatting
        24812, -- 2312.09249 ZeroRF: Fast Sparse View 360° Reconstruction with Zero Pretraining
        24820, -- 2312.09305 Stable Score Distillation for High-Quality 3D Generation
        24821, -- 2312.09313 LatentEditor: Text Driven Local Editing of 3D Scenes
        24831, -- 2312.09527 TIFace: Improving Facial Reconstruction through Tensorial Radiance Fie
        24852, -- 2312.10034 SlimmeRF: Slimmable Radiance Fields
        24923, -- 2312.11360 Paint-it: Text-to-Texture Synthesis via Deep Convolutional Texture Map
        24932, -- 2312.11458 GauFRe: Gaussian Deformation Fields for Real-time Dynamic Novel View S
        24933, -- 2312.11459 VolumeDiffusion: Flexible Text-to-3D Generation with Efficient Volumet
        24948, -- 2312.11535 Customize-It-3D: High-Quality 3D Creation from A Single Image Using Su
        24949, -- 2312.11537 FastSR-NeRF: Improving NeRF Efficiency on Consumer Devices with A Simp
        24965, -- 2312.11841 MixRT: Mixed Neural Representations For Real-Time NeRF Rendering
        24988, -- 2312.12337 pixelSplat: 3D Gaussian Splats from Image Pairs for Scalable Generaliz
        25034, -- 2312.12877 Relightable and Animatable Neural Avatars from Videos
        25039, -- 2312.13102 SpecNeRF: Gaussian Directional Encoding for Specular Reflections
        25052, -- 2312.13271 Repaint123: Fast and High-quality One Image to 3D Generation with Prog
        25053, -- 2312.13285 UniSDF: Unifying Neural Representations for High-Fidelity 3D Reconstru
        25055, -- 2312.13299 Compact 3D Scene Representation via Self-Organizing Gaussian Grids
        25062, -- 2312.13324 ShowRoom3D: Text to High-Quality 3D Room Generation Using 3D Priors
        25066, -- 2312.13469 Neural feels with neural fields: Visuo-tactile perception for in-hand
        25073, -- 2312.13663 Free-Editor: Zero-shot Text-driven 3D Scene Editing
        25077, -- 2312.13729 Gaussian Splatting with NeRF-based Color and Opacity
        25090, -- 2312.13980 Carve3D: Improving Multi-view Reconstruction Consistency for Diffusion
        25145, -- 2312.14937 SC-GS: Sparse-Controlled Gaussian Splatting for Editable Dynamic Scene
        25156, -- 2312.15059 Deformable 3D Gaussian Splatting for Animatable Human Avatars
        25168, -- 2312.15258 Human101: Training 100+FPS Human Gaussians in 100s from 1 View
        25217, -- 2312.16084 LangSplat: 3D Language Gaussian Splatting
        25231, -- 2312.16256 DL3DV-10K: A Large-Scale Scene Dataset for Deep Learning-based 3D Visi
        25242, -- 2312.16457 City-on-Web: Real-time Neural Rendering of Large-scale Scenes on the W
        25256, -- 2312.16812 Spacetime Gaussian Feature Splatting for Real-Time Dynamic View Synthe
        25281, -- 2312.17225 4DGen: Grounded 4D Content Generation with Spatial-temporal Consistenc
        25292, -- 2312.17250 iFusion: Inverting Diffusion for Pose-Free Reconstruction from Sparse
        25362, -- 2401.00604 SteinDreamer: Variance Reduction for Text-to-3D Score Distillation via
        25378, -- 2401.00834 Deblurring 3D Gaussian Splatting
        25390, -- 2401.00909 Taming Mode Collapse in Score Distillation for Text-to-3D Generation
        25415, -- 2401.01339 Street Gaussians: Modeling Dynamic Urban Scenes with Gaussian Splattin
        25433, -- 2401.01647 SIGNeRF: Scene Integrated Generation for Neural Radiance Fields
        25437, -- 2401.01702 Image Sculpting: Precise Object Editing with 3D Geometry Control
        25486, -- 2401.02357 Fit-NGP: Fitting Object Models to Neural Graphics Primitives
        25491, -- 2401.02411 What You See is What You GAN: Rendering Every Pixel for High-Fidelity
        25520, -- 2401.02957 Denoising Vision Transformers
        25574, -- 2401.03890 A Survey on 3D Gaussian Splatting
        25588, -- 2401.04099 AGG: Amortized Generative 3D Gaussians for Single Image to 3D
        25659, -- 2401.05335 InseRF: Text-Driven Generative Object Insertion in Neural 3D Scenes
        25676, -- 2401.05583 Diffusion Priors for Dynamic View Synthesis from Monocular Videos
        25692, -- 2401.05750 GO-NeRF: Generating Objects in Neural Radiance Fields for Virtual Real
        25707, -- 2401.06003 TRIPS: Trilinear Point Splatting for Real-Time Radiance Field Renderin
        25728, -- 2401.06191 TriNeRFLet: A Wavelet Based Triplane NeRF Representation
        25824, -- 2401.07727 HexaGen3D: StableDiffusion is just one step away from Fast and Diverse
        25923, -- 2401.09050 Consistent3D: Towards Consistent High-Fidelity Text-to-3D Generation w
        25944, -- 2401.09386 Tri$^{2}$-plane: Thinking Head Avatar via Feature Pyramid
        25946, -- 2401.09416 TextureDreamer: Image-guided Texture Synthesis through Geometry-aware
        25948, -- 2401.09419 GARField: Group Anything with Radiance Fields
        25972, -- 2401.09720 GaussianBody: Clothed Human Reconstruction via 3d Gaussian Splatting
        26052, -- 2401.10786 Sat2Scene: 3D Urban Scene Generation from Satellite Images with Diffus
        26173, -- 2401.12517 DDMI: Domain-Agnostic Latent Diffusion Models for Synthesizing High-Qu
        26204, -- 2401.12979 GALA: Generating Animatable Layered Assets from a Single Scan
        26293, -- 2401.14257 Sketch2NeRF: Multi-view Sketch-guided Text-to-3D Generation
        26338, -- 2401.14828 TIP-Editor: An Accurate 3D Editor Following Both Text-Prompts And Imag
        26364, -- 2401.15318 Gaussian Splashing: Unified Particles for Versatile Motion Synthesis a
        26459, -- 2401.16663 VR-GS: A Physical Dynamics-Aware Interactive Gaussian Splatting System
        26521, -- 2401.17664 Image Anything: Towards Reasoning-coherent and Training-free Multi-mod
        26526, -- 2401.17807 Advances in 3D Generation: A Survey
        26534, -- 2401.17895 ReplaceAnything3D:Text-Guided 3D Scene Editing with Compositional Neur
        26546, -- 2401.18075 CARFF: Conditional Auto-encoded Radiance Field for 3D Scene Forecastin
        26586, -- 2402.00763 360-GS: Layout-guided Panoramic Gaussian Splatting For Indoor Roaming
        26595, -- 2402.00827 GaussianStyle: Gaussian Head Avatar via StyleGAN
        26606, -- 2402.00867 AToM: Amortized Text-to-Mesh using 2D Diffusion
        26660, -- 2402.01459 GaMeS: Mesh-Based Adapting and Modification of Gaussian Splatting
        26667, -- 2402.01524 HyperPlanes: Hypernetwork Approach to Rapid NeRF Adaptation
        26807, -- 2402.02972 Retrieval-Augmented Score Distillation for Text-to-3D Generation
        26844, -- 2402.03307 4D-Rotor Gaussian Splatting: Towards Efficient Novel View Synthesis fo
        26852, -- 2402.03445 Denoising Diffusion via Image-Based Rendering
        26908, -- 2402.03908 EscherNet: A Generative Model for Scalable View Synthesis
        26962, -- 2402.04554 BirdNeRF: Fast Neural Reconstruction of Large-Scale Scenes From Aerial
        26977, -- 2402.04648 OV-NeRF: Open-vocabulary Neural Radiance Fields with Vision and Langua
        26986, -- 2402.04796 Mesh-based Gaussian Splatting for Real-time Large-scale Deformation
        26989, -- 2402.04829 NeRF as a Non-Distant Environment Emitter in Physics-based Inverse Ren
        27005, -- 2402.05054 LGM: Large Multi-View Gaussian Model for High-Resolution 3D Content Cr
        27044, -- 2402.05568 Neural Graphics Primitives-based Deformable Image Registration for On-
        27060, -- 2402.05746 Editable Scene Simulation for Autonomous Driving via Collaborative LLM
        27264, -- 2402.08622 NeRF Analogies: Example-Based Visual Attribute Transfer for NeRFs
        27373, -- 2402.10128 GES: Generalized Exponential Splatting for Efficient Radiance Field Re
        27397, -- 2402.10403 Polyhedral Complex Derivation from Piecewise Trilinear Networks
        27468, -- 2402.11141 Semantically-aware Neural Radiance Fields for Visual Scene Understandi
        27610, -- 2402.12377 Binary Opacity Grids: Capturing Fine Geometric Detail for Mesh-Based V
        27694, -- 2402.13251 FlashTex: Fast Relightable Mesh Texturing with LightControlNet
        27695, -- 2402.13252 Improving Robustness for Joint Optimization of Camera Poses and Decomp
        27698, -- 2402.13255 How NeRFs and 3D Gaussian Splatting are Reshaping SLAM: a Survey
        27816, -- 2402.14650 GaussianPro: 3D Gaussian Splatting with Progressive Propagation
        27834, -- 2402.14792 Consolidating Attention Features for Multi-view Image Editing
        27936, -- 2402.15870 Spec-Gaussian: Anisotropic View-Dependent Appearance for 3D Gaussian S
        28016, -- 2402.16936 Disentangled 3D Scene Generation with Layout Learning
        28057, -- 2402.17427 VastGaussian: Vast 3D Gaussians for Large Scene Reconstruction
        28126, -- 2402.18152 Boosting Neural Representations for Videos with a Conditional Decoder
        28140, -- 2402.18305 NERV++: An Enhanced Implicit Neural Video Representation
        28321, -- 2403.01444 3DGStream: On-the-Fly Training of 3D Gaussians for Efficient Streaming
        28345, -- 2403.01807 ViewDiff: 3D-Consistent Image Generation with Text-to-Image Models
        28371, -- 2403.02234 3DTopia: Large Text-to-3D Generation Model with Hybrid Diffusion Prior
        28387, -- 2403.02460 MagicClay: Sculpting Meshes With Generative Neural Fields
        28493, -- 2403.04116 Radiative Gaussian Splatting for Efficient X-ray Novel View Synthesis
        28571, -- 2403.05154 GSEdit: Efficient Text-Guided Editing of 3D Objects via Gaussian Splat
        28622, -- 2403.06092 Is Vanilla MLP in Neural Radiance Field Enough for Few-shot View Synth
        28661, -- 2403.06738 V3D: Video Diffusion Models are Effective 3D Generators
        28742, -- 2403.07807 StyleGaussian: Instant 3D Style Transfer with Gaussian Splatting
        28788, -- 2403.08551 GaussianImage: 1000 FPS Image Representation and Compression by 2D Gau
        28857, -- 2403.09419 RoDUS: Robust Decomposition of Static and Dynamic Elements in Urban Sc
        28873, -- 2403.09625 Make-Your-3D: Fast and Consistent Subject-Driven 3D Content Generation
        28928, -- 2403.10427 SWAG: Splatting in the Wild images with Appearance-conditioned Gaussia
        28968, -- 2403.10997 N2F2: Hierarchical Scene Understanding with Nested Neural Feature Fiel
        28975, -- 2403.11056 Analytic-Splatting: Anti-Aliased 3D Gaussian Splatting via Analytic In
        28983, -- 2403.11131 Omni-Recon: Harnessing Image-based Rendering for General-Purpose Neura
        28991, -- 2403.11273 BrightDreamer: Generic 3D Gaussian Generative Framework for Fast Text-
        29008, -- 2403.11447 Motion-aware 3D Gaussian Splatting for Efficient Dynamic Scene Reconst
        29019, -- 2403.11589 UV Gaussians: Joint Learning of Mesh Deformation and Gaussian Textures
        29040, -- 2403.11831 BAD-Gaussians: Bundle Adjusted Deblur Gaussian Splatting
        29045, -- 2403.11865 Exploring Multi-modal Neural Scene Representations With Applications o
        29056, -- 2403.12008 SV3D: Novel Multi-view Synthesis and 3D Generation from a Single Image
        29069, -- 2403.12032 Generic 3D Diffusion Adapter Using Controlled Multi-View Editing
        29099, -- 2403.12535 High-Fidelity SLAM Using Gaussian Splatting with Rendering-Guided Dens
        29114, -- 2403.12722 HUGS: Holistic Urban 3D Scene Understanding via Gaussian Splatting
        29125, -- 2403.12870 PoNQ: a Neural QEM-based Mesh Representation
        29130, -- 2403.12906 TexDreamer: Towards Zero-Shot High-Fidelity 3D Human Texture Generatio
        29136, -- 2403.12957 GVGEN: Text-to-3D Generation with Volumetric Representation
        29170, -- 2403.13289 Text-to-3D Shape Generation
        29216, -- 2403.13806 RadSplat: Radiance Field-Informed Gaussian Splatting for Robust Real-T
        29270, -- 2403.14554 Gaussian Frosting: Editable Complex Radiance Fields with Real-Time Ren
        29278, -- 2403.14611 Explorative Inbetweening of Time and Space
        29281, -- 2403.14621 GRM: Large Gaussian Reconstruction Model for Efficient 3D Reconstructi
        29306, -- 2403.14939 STAG4D: Spatial-Temporal Anchored Generative 4D Gaussians
        29308, -- 2403.14966 DreamFlow: High-Quality Text-to-3D Generation by Approximating Probabi
        29359, -- 2403.15612 InterFusion: Text-Driven Generation of 3D Human-Object Interaction
        29364, -- 2403.15704 Gaussian in the Wild: 3D Gaussian Splatting for Unconstrained Image Co
        29365, -- 2403.15705 SUP-NeRF: A Streamlined Unification of Pose Estimation and NeRF for Mo
        29388, -- 2403.16080 PKU-DyMVHumans: A Multi-View Video Benchmark for High-Fidelity Dynamic
        29389, -- 2403.16092 Are NeRFs ready for autonomous driving? Towards closing the real-to-si
        29410, -- 2403.16481 REFRAME: Reflective Surface Real-Time Rendering for Mobile Devices
        29431, -- 2403.16897 Make-It-Vivid: Dressing Your Animatable Biped Cartoon Characters from
        29436, -- 2403.16964 GSDF: 3DGS Meets SDF for Improved Rendering and Reconstruction
        29444, -- 2403.17001 VP3D: Unleashing 2D Visual Prompt for Text-to-3D Generation
        29456, -- 2403.17237 DreamPolisher: Towards High-Quality Text-to-3D Generation via Geometri
        29470, -- 2403.17607 Fully-fused Multi-Layer Perceptrons on Intel Data Center GPUs
        29495, -- 2403.17888 2D Gaussian Splatting for Geometrically Accurate Radiance Fields
        29497, -- 2403.17898 Octree-GS: Towards Consistent Real-time Rendering with LOD-Structured
        29502, -- 2403.17920 TC4D: Trajectory-Conditioned Text-to-4D Generation
        29506, -- 2403.17931 Track Everything Everywhere Fast and Robustly
        29570, -- 2403.18820 MetaCap: Meta-learning Priors from Multi-View Imagery for Sparse-view
        29600, -- 2403.19319 Mesh2NeRF: Direct Mesh Supervision for Neural Radiance Field Represent
        29618, -- 2403.19549 GlORIE-SLAM: Globally Optimized RGB-only Implicit Encoding Point Cloud
        29633, -- 2403.19655 GaussianCube: A Structured and Explicit Radiance Representation for 3D
        29673, -- 2403.20275 Snap-it, Tap-it, Splat-it: Tactile-Informed 3D Gaussian Splatting for
        29750, -- 2404.00923 MM3DGS SLAM: Multi-modal 3D Gaussian Splatting for SLAM Using Vision,
        29756, -- 2404.00987 FlexiDreamer: Single Image-to-3D Generation with FlexiCubes
        29766, -- 2404.01082 The state-of-the-art in Cardiac MRI Reconstruction: Results of the CMR
        29770, -- 2404.01133 CityGaussian: Real-time High-quality Large-Scale Scene Rendering with
        29777, -- 2404.01223 Feature Splatting: Language-Driven Physics-Based Scene Synthesis and E
        29793, -- 2404.01300 NeRF-MAE: Masked AutoEncoders for Self-Supervised 3D Representation Le
        29834, -- 2404.01810 GS2Mesh: Surface Reconstruction from Gaussian Splatting via Novel Ster
        29858, -- 2404.02152 GeneAvatar: Generic Expression-Aware Volumetric Head Avatar Editing fr
        29869, -- 2404.02410 TCLC-GS: Tightly Coupled LiDAR-Camera Gaussian Splatting for Autonomou
        29933, -- 2404.03421 Gen3DSR: Generalizable 3D Scene Reconstruction via Divide and Conquer
        29947, -- 2404.03575 DreamScene: 3D Gaussian-based Text-to-3D Scene Generation via Formatio
        29972, -- 2404.03736 SC4D: Sparse-Controlled Video-to-4D Generation and Motion Transfer
        29997, -- 2404.04211 Robust Gaussian Splatting
        30021, -- 2404.04526 DATENeRF: Depth-Aware Text-based Editing of NeRFs
        30044, -- 2404.04913 CodecNeRF: Toward Fast Encoding and Decoding, Compact, and High-qualit
        30119, -- 2404.06091 Hash3D: Training-free Acceleration for 3D Generation
        30120, -- 2404.06109 Revising Densification in Gaussian Splatting
        30146, -- 2404.06429 Magic-Boost: Boost 3D Generation with Multi-View Conditioned Diffusion
        30153, -- 2404.06493 Flying with Photons: Rendering Novel Views of Propagating Light
        30154, -- 2404.06507 Reconstructing Hand-Held Objects in 3D from Images and Videos
        30169, -- 2404.06903 DreamScene360: Unconstrained Text-to-3D Scene Generation with Panorami
        30248, -- 2404.07977 Gaga: Group Any Gaussians via 3D-aware Memory Bank
        30256, -- 2404.07991 GoMAvatar: Efficient Animatable Human Modeling from Monocular Video Us
        30268, -- 2404.08252 MonoPatchNeRF: Improving Neural Radiance Fields with Patch-based Monoc
        30344, -- 2404.09458 CompGS: Efficient 3D Scene Representation via Compressed Gaussian Spla
        30359, -- 2404.09591 3D Gaussian Splatting as Markov Chain Monte Carlo
        30380, -- 2404.09833 Video2Game: Real-time, Interactive, Realistic and Browser-Compatible E
        30392, -- 2404.09995 Taming Latent Diffusion Model for Neural Radiance Field Inpainting
        30515, -- 2404.12139 Omniview-Tuning: Boosting Viewpoint Invariance of Vision-Language Pre-
        30530, -- 2404.12333 Customizing Text-to-Image Diffusion with Object Viewpoint Control
        30538, -- 2404.12378 6Img-to-3D: Few-Image Large-Scale Outdoor Driving Scene Reconstruction
        30540, -- 2404.12385 MeshLRM: Large Reconstruction Model for High-Quality Meshes
        30561, -- 2404.12547 Evaluating Alternatives to SFM Point Cloud Initialization for Gaussian
        30621, -- 2404.13679 GScream: Learning 3D Geometry and Feature Consistent Gaussian Splattin
        30649, -- 2404.14351 Scene Coordinate Reconstruction: Posing of Image Collections via Incre
        30709, -- 2404.15259 FlowMap: High-Quality Camera Poses, Intrinsics, and Depth via Gradient
        30710, -- 2404.15264 TalkingGaussian: Structure-Persistent 3D Talking Head Synthesis via Ga
        30756, -- 2404.16221 NeRF-XL: Scaling NeRFs with Multiple GPUs
        30780, -- 2404.16748 TELA: Text to Layer-wise 3D Clothed Human Generation
        30831, -- 2404.17569 MaPa: Text-driven Photorealistic Material Painting for 3D Shapes
        30847, -- 2404.17774 High-quality Surface Reconstruction using Gaussian Surfels
        30911, -- 2404.19149 SAGS: Structure-Aware 3D Gaussian Splatting
        30924, -- 2404.19398 3D Gaussian Blendshapes for Head Avatar Animation
        30930, -- 2404.19525 MicroDreamer: Efficient 3D Generation in $\sim$20 Seconds by Score-bas
        30938, -- 2404.19702 GS-LRM: Large Reconstruction Model for 3D Gaussian Splatting
        30947, -- 2404.19760 Lightplane: Highly-Scalable Components for Neural 3D Fields
        30985, -- 2405.00676 Spectrally Pruned Gaussian Fields with Neural Compensation
        31165, -- 2405.05663 RPBG: Towards Robust Neural Point-based Graphics in the Wild
        31365, -- 2405.10314 CAT3D: Create Anything in 3D with Multi-View Diffusion Models
        31376, -- 2405.10531 Nonparametric Teaching of Implicit Neural Representations
        31439, -- 2405.12069 Gaussian Head & Shoulders: High Fidelity Neural Upper Body Avatars wit
        31457, -- 2405.12420 GarmentDreamer: 3DGS Guided Garment Synthesis with Diverse Geometry an
        31628, -- 2405.14847 Neural Directional Encoding for Efficient and Accurate View-Dependent
        31638, -- 2405.14871 NeRF-Casting: Improved View-Dependent Appearance with Consistent Refle
        31660, -- 2405.15125 HDR-GS: Efficient High Dynamic Range Novel View Synthesis at 1000x Spe
        31732, -- 2405.15891 Score Distillation via Reparametrized DDIM
        31777, -- 2405.16570 ID-to-3D: Expressive ID-guided 3D Heads via Score Distillation Samplin
        31798, -- 2405.16807 Extreme Compression of Adaptive Neural Images
        31826, -- 2405.17176 DreamMat: High-quality PBR Material Generation with Geometry- and Ligh
        31849, -- 2405.17421 MoSca: Dynamic Gaussian Fusion from Casual Videos via 4D Motion Scaffo
        31924, -- 2405.18213 NeRAF: 3D Scene Infused Neural Radiance and Acoustic Fields
        31946, -- 2405.18416 3D StreetUnveiler with Semantic-Aware 2DGS
        31950, -- 2405.18426 GFlow: Recovering 4D World from Monocular Video
        32008, -- 2405.19331 NPGA: Neural Parametric Gaussian Avatars
        32032, -- 2405.19678 View-Consistent Hierarchical 3D Segmentation Using Ultrametric Feature
        32084, -- 2405.20283 TetSphere Splatting: Representing High-Quality Geometry with Lagrangia
        32093, -- 2405.20327 GECO: Generative Image-to-3D within a SECOnd
        32098, -- 2405.20343 Unique3D: High-Quality and Efficient 3D Mesh Generation from a Single
        32117, -- 2405.20674 4Diffusion: Multi-view Video Diffusion Model for 4D Generation
        32128, -- 2405.20851 MegActor: Harness the Power of Raw Video for Vivid Portrait Animation
        32179, -- 2406.00440 Topo4D: Topology-Preserving Gaussian Splatting for High-Fidelity 4D He
        32181, -- 2406.00448 Bilateral Guided Radiance Field Processing
        32253, -- 2406.01597 End-to-End Rate-Distortion Optimized 3D Gaussian Representation
        32301, -- 2406.02407 WE-GS: An In-the-wild Efficient 3D Gaussian Representation for Unconst
        32354, -- 2406.02968 GSGAN: Adversarial Learning for Hierarchical Generation of 3D Gaussian
        32365, -- 2406.03184 Ouroboros3D: Image-to-3D Generation via 3D-aware Recursive Diffusion
        32436, -- 2406.04251 Improving Gaussian Splatting with Localized Points Management
        32507, -- 2406.04875 3DRealCar: An In-the-wild RGB-D Car Dataset with 360-degree Views
        32603, -- 2406.06133 ExtraNeRF: Visibility-Aware View Extrapolation of Neural Radiance Fiel
        32608, -- 2406.06216 Lighting Every Darkness with 3DGS: Fast Training and Real-Time Renderi
        32639, -- 2406.06523 NaRCan: Natural Refined Canonical Image with Integration of Diffusion
        32642, -- 2406.06527 IllumiNeRF: 3D Relighting Without Inverse Rendering
        32712, -- 2406.07431 Active Scout: Multi-Target Tracking Using Neural Radiance Fields in De
        32785, -- 2406.08176 Category-level Neural Field for Reconstruction of Partially Observed O
        32827, -- 2406.08659 Vivid-ZOO: Multi-View Video Generation with Diffusion Model
        32835, -- 2406.08759 GaussianForest: Hierarchical-Hybrid 3D Gaussian Splatting for Compress
        32845, -- 2406.08894 OpenMaterial: A Comprehensive Dataset of Complex Materials for 3D Reco
        32889, -- 2406.09371 LRM-Zero: Training Large Reconstruction Models with Synthesized Data
        32890, -- 2406.09383 Multiagent Multitraversal Multimodal Self-Driving: Open MARS Dataset
        32892, -- 2406.09394 WonderWorld: Interactive 3D Scene Generation from a Single Image
        32898, -- 2406.09404 ConsistDreamer: 3D-Consistent 2D Diffusion for High-Fidelity Scene Edi
        32989, -- 2406.10373 Wild-GS: Real-Time Novel View Synthesis from Unconstrained Photo Colle
        33172, -- 2406.11840 LLaNA: Large Language and NeRF Assistant
        33209, -- 2406.12121 TutteNet: Injective 3D Deformations by Composition of 2D Mesh Deformat
        33300, -- 2406.13099 Sampling 3D Gaussian Scenes in Seconds with Latent Diffusion Models
        33323, -- 2406.13393 Style-NeRF2NeRF: 3D Style Transfer From Style-Aligned Multi-View Image
        33523, -- 2406.15811 PointDreamer: Zero-shot 3D Textured Mesh Reconstruction from Colored P
        33536, -- 2406.16038 LiveScene: Language Embedding Interactive Radiance Fields for Physical
        33556, -- 2406.16273 YouDream: Generating Anatomically Controllable Consistent Text-to-3D A
        33589, -- 2406.16695 Geometry-Aware Score Distillation via 3D Consistent Noising and Gradie
        33645, -- 2406.17345 NerfBaselines: Consistent and Reproducible Evaluation of Novel View Sy
        33665, -- 2406.17601 Director3D: Real-world Camera Trajectory and 3D Scene Generation from
        33740, -- 2406.18462 GaussianDreamerPro: Text to Manipulable 3D Gaussians with Highly Enhan
        33751, -- 2406.18544 GS-ROR$^2$: Bidirectional-guided 3DGS and SDF for Reflective Object Re
        33819, -- 2406.19434 Lightweight Predictive 3D Gaussian Splats
        33857, -- 2406.20055 SpotlessSplats: Ignoring Distractors in 3D Gaussian Splatting
        33891, -- 2407.00367 SVG: 3D Stereoscopic Video Generation via Denoising Frame Matrix
        33997, -- 2407.01866 Image-GS: Content-Adaptive Image Representation via 2D Gaussians
        34017, -- 2407.02040 ScaleDreamer: Scalable Text-to-3D Synthesis with Asynchronous Score Di
        34052, -- 2407.02445 Meta 3D AssetGen: Text-to-Mesh Generation with High-Quality Geometry,
        34065, -- 2407.02599 Meta 3D Gen
        34118, -- 2407.03330 Efficient Visibility Approximation for Game AI using Neural Omnidirect
        34323, -- 2407.06150 PanDORA: Casual HDR Radiance Acquisition for Indoor Scenes
        34347, -- 2407.06397 RRM: Relightable assets using Radiance guided Material extraction
        34358, -- 2407.06516 VQA-Diff: Exploiting VQA and Diffusion for Zero-Shot Image-to-3D Vehic
        34374, -- 2407.06842 Chat-Edit-3D: Interactive 3D Scene Editing via Text Prompts
        34377, -- 2407.06938 RodinHD: High-Fidelity 3D Avatar Generation with Diffusion Models
        34394, -- 2407.07090 3D Gaussian Ray Tracing: Fast Tracing of Particle Scenes
        34401, -- 2407.07220 Reference-based Controllable Scene Stylization with Gaussian Splatting
        34405, -- 2407.07284 MIGS: Multi-Identity Gaussian Splatting via Tensor Decomposition
        34486, -- 2407.08447 WildGaussians: 3D Gaussian Splatting in the Wild
        34572, -- 2407.09473 StyleSplat: 3D Object Style Transfer with Gaussian Splatting
        34584, -- 2407.09679 Physics-Informed Learning of Characteristic Trajectories for Smoke Rec
        34587, -- 2407.09733 Textured-GS: Gaussian Splatting with Spatially Defined Color and Opaci
        34633, -- 2407.10330 Tree-D Fusion: Simulation-Ready Tree Dataset from Single Images with D
        34657, -- 2407.10707 Interactive Rendering of Relightable and Animatable Gaussian Avatars
        34706, -- 2407.11174 iHuman: Instant Animatable Digital Humans From Monocular Videos
        34798, -- 2407.12306 Splatfacto-W: A Nerfstudio Implementation of Gaussian Splatting for Un
        34829, -- 2407.12667 SG-NeRF: Neural Surface Reconstruction with Scene Graph Optimization
        34963, -- 2407.14257 SparseCraft: Few-Shot Neural Reconstruction through Stereopsis Guided
        35017, -- 2407.15212 Surfel-based Gaussian Inverse Rendering for Fast and Relightable Dynam
        35027, -- 2407.15337 ThermalNeRF: Thermal Radiance Fields
        35097, -- 2407.16260 DreamDissector: Learning Disentangled Text-to-3D Generation from 2D Di
        35141, -- 2407.16988 DreamCar: Leveraging Car-specific Prior for in-the-wild 3D Car Reconst
        35168, -- 2407.17470 SV4D: Dynamic 3D Content Generation with Multi-Frame and Multi-View Co
        35254, -- 2407.19108 ObjectCarver: Semi-automatic segmentation, reconstruction and separati
        35272, -- 2407.19542 UniVoxel: Fast Inverse Rendering by Unified Voxelization of Scene Repr
        35336, -- 2407.20727 SceneTeller: Language-to-3D Scene Generation
        35353, -- 2407.21047 PAV: Personalized Head Avatar from Unstructured Video Collection
        35403, -- 2408.00083 Localized Gaussian Splatting Editing with Contextual Awareness
        35488, -- 2408.01291 TexGen: Text-Guided 3D Texture Generation with Multi-view Sampling and
        35612, -- 2408.03356 RayGauss: Volumetric Gaussian-Based Ray Casting for Photorealistic Nov
        35632, -- 2408.03822 Compact 3D Gaussian Splatting for Static and Dynamic Radiance Fields
        35740, -- 2408.05938 Deep Geometric Moments Promote Shape Consistency in Text-to-3D Generat
        35829, -- 2408.07416 Rethinking Open-Vocabulary Segmentation of Radiance Fields in 3D Space
        35838, -- 2408.07540 3D Gaussian Editing with A Single Image
        35871, -- 2408.08206 WaterSplatting: Fast Underwater 3D Scene Reconstruction Using Gaussian
        35927, -- 2408.09126 Barbie: Text to Barbie-Style 3D Avatars
        35985, -- 2408.10258 NeRF-US: Removing Ultrasound Imaging Artifacts from Neural Radiance Fi
        36080, -- 2408.11465 MeTTA: Single-View to 3D Textured Mesh Reconstruction with Test-Time A
        36128, -- 2408.12282 Subsurface Scattering for 3D Gaussian Splatting
        36181, -- 2408.13252 LayerPano3D: Layered 3D Panorama for Hyper-Immersive Scene Generation
        36214, -- 2408.13912 Splatt3R: Zero-shot Gaussian Splatting from Uncalibrated Image Pairs
        36258, -- 2408.14732 OctFusion: Octree-based Diffusion Models for 3D Shape Generation
        36390, -- 2408.16760 OmniRe: Omni Urban Scene Reconstruction
        36396, -- 2408.16866 GameIR: A Large-Scale Synthesized Ground-Truth Dataset for Image Resto
        36615, -- 2409.03456 LM-Gaussian: Boost Sparse-view 3D Gaussian Splatting with Large Model
        36746, -- 2409.06703 LEIA: Latent View-invariant Embeddings for Implicit 3D Articulation
        36765, -- 2409.07129 MVLLaVA: An Intelligent Agent for Unified and Flexible Novel View Synt
        36768, -- 2409.07179 Phy124: Fast Physics-Driven 4D Content Generation from a Single Image
        36781, -- 2409.07441 Instant Facial Gaussians Translator for Relightable and Interactable F
        36784, -- 2409.07452 Hi3D: Pursuing High-Resolution Image-to-3D Generation with Video Diffu
        36819, -- 2409.08270 FlashSplat: 2D to 3D Gaussian Splatting Segmentation Solved Optimally
        36825, -- 2409.08353 Robust Dual Gaussian Splatting for Immersive Human-centric Volumetric
        36856, -- 2409.08947 A Diffusion Approach to Radiance Field Relighting using Multi-Illumina
        36963, -- 2409.10836 Single-Layer Learnable Activation for Implicit Neural Representation (
        36983, -- 2409.11211 SplatFields: Neural Gaussian Splats for Sparse 3D and 4D Reconstructio
        37057, -- 2409.12193 Vista3D: Unravel the 3D Darkside of a Single Image
        37087, -- 2409.12892 3DGS-LM: Faster Gaussian-Splatting Optimization with Levenberg-Marquar
        37226, -- 2409.15273 MaterialFusion: Enhancing Inverse Rendering with Material Diffusion Pr
        37334, -- 2409.17145 DreamWaltz-G: Expressive 3D Gaussian Avatars from Skeleton-Guided 2D D
        37384, -- 2409.17988 Deblur e-NeRF: NeRF from Motion-Blurred Events under High-speed or Low
        37470, -- 2409.19405 G3R: Gradient Guided Generalizable Reconstruction
        37496, -- 2409.19702 RNG: Relightable Neural Gaussians
        37534, -- 2409.20140 RISE-SDF: a Relightable Information-Shared Signed Distance Field for G
        37659, -- 2410.01521 MiraGe: Editable 2D Images using Gaussian Splatting
        37694, -- 2410.01804 EVER: Exact Volumetric Ellipsoid Rendering for Real-time View Synthesi
        37722, -- 2410.02103 MVGS: Multi-view-regulated Gaussian Splatting for Novel View Synthesis
        37778, -- 2410.02619 GI-GS: Global Illumination Decomposition on Gaussian Splatting for Inv
        38186, -- 2410.07160 TextToon: Real-Time Text Toonify Head Avatar from Single Video
        38226, -- 2410.07707 MotionGS: Exploring Explicit Motion Guidance for Deformable 3D Gaussia
        38244, -- 2410.08017 Fast Feedforward 3D Gaussian Splatting Compression
        38321, -- 2410.08941 MeshGS: Adaptive Mesh-Aligned Gaussian Splatting for High-Quality Rend
        38409, -- 2410.10122 MuseTalk: Real-Time High-Fidelity Video Dubbing via Spatio-Temporal Sa
        38631, -- 2410.12781 Long-LRM: Long-sequence Large Reconstruction Model for Wide-coverage G
        38652, -- 2410.12928 DreamCraft3D++: Efficient Hierarchical 3D Generation with Multi-Plane
        38714, -- 2410.13571 DriveDreamer4D: World Models Are Effective Data Machines for 4D Drivin
        38949, -- 2410.16271 FrugalNeRF: Fast Convergence for Few-shot Novel View Synthesis without
        38984, -- 2410.16770 The Scene Language: Representing Scenes with Programs, Words, and Embe
        39015, -- 2410.17242 LVSM: A Large View Synthesis Model with Minimal 3D Inductive Bias
        39143, -- 2410.18956 Large Spatial Model: End-to-end Unposed Images to Semantic 3D
        39148, -- 2410.18974 3D-Adapter: Geometry-Consistent Multi-View Diffusion for High-Quality
        39222, -- 2410.20220 Neural Fields in Robotics: A Survey
        39330, -- 2410.22070 FreeGaussian: Guidance-free Controllable 3D Gaussian Splats with Flow
        39435, -- 2410.23800 SOAR: Self-Occluded Avatar Recovery from a Single Video In the Wild
        39498, -- 2411.00399 StyleTex: Style Image-Guided Texture Generation for 3D Models
        39527, -- 2411.00771 CityGaussianV2: Efficient and Geometrically Accurate Reconstruction fo
        39574, -- 2411.01602 DreamPolish: Domain Score Distillation With Progressive Geometry Gener
        39581, -- 2411.01853 GVKF: Gaussian Voxel Kernel Functions for Highly Efficient Surface Rec
        39840, -- 2411.06307 Acoustic Volume Rendering for Neural Impulse Response Fields
        39842, -- 2411.06390 SplatFormer: Point Transformer for Robust 3D Gaussian Splatting
        39855, -- 2411.06602 Adaptive and Temporally Consistent Gaussian Surfels for Multi-view Dyn
        39939, -- 2411.08033 GaussianAnything: Interactive Point Cloud Flow Matching For 3D Object
        40060, -- 2411.10546 The Oxford Spires Dataset: Benchmarking Large-Scale LiDAR-Visual Local
        40105, -- 2411.11374 LeC$^2$O-NeRF: Learning Continuous and Compact Large-Scale Occupancy f
        40221, -- 2411.13549 Generating 3D-Consistent Videos from Unposed Internet Photos
        40252, -- 2411.14208 Novel View Extrapolation with Video Diffusion Priors
        40266, -- 2411.14423 PhysFlow: Unleashing the Potential of Multi-modal Foundation Models an
        40305, -- 2411.14974 3D Convex Splatting: Radiance Field Rendering with 3D Smooth Convexes
        40372, -- 2411.15604 FATE: Full-head Gaussian Avatar with Textural Editing from Monocular V
        40401, -- 2411.16076 Geometry Distributions
        40409, -- 2411.16157 MVGenMaster: Scaling Multi-View Generation from Any Image via 3D Prior
        40431, -- 2411.16443 SplatFlow: Multi-View Rectified Flow Model for 3D Gaussian Splatting S
        40471, -- 2411.16877 PreF3R: Pose-Free Feed-Forward 3D Gaussian Splatting from Variable-len
        40473, -- 2411.16898 G2SDF: Surface Reconstruction from Explicit Gaussians with Implicit SD
        40520, -- 2411.17489 Puzzle Similarity: A Perceptually-guided Cross-Reference Metric for Ar
        40564, -- 2411.17982 HI-SLAM2: Geometry-Aware Gaussian SLAM for Fast Monocular Scene Recons
        40591, -- 2411.18311 Neural Surface Priors for Editable Gaussian Splatting
        40616, -- 2411.18624 GeneMAN: Generalizable Single-Image 3D Human Reconstruction from Multi
        40660, -- 2411.19233 Gaussians-to-Life: Text-Driven Animation of 3D Gaussian Splatting Scen
        40702, -- 2411.19654 TexGaussian: Generating High-quality PBR Material via Octree-based 3D
        40921, -- 2412.02690 FoundHand: Large-Scale Domain-Specific Learning for Controllable Hand
        40950, -- 2412.03077 RoDyGS: Robust Dynamic Gaussian Splatting for Casual Videos
        40987, -- 2412.03526 Feed-Forward Bullet-Time Reconstruction of Dynamic Scenes from Monocul
        41021, -- 2412.03844 HybridGS: Decoupling Transients and Statics with 2D and 3D Gaussian Sp
        41022, -- 2412.03848 INRetouch: Context Aware Implicit Neural Representation for Photograph
        41025, -- 2412.03910 DGNS: Deformable Gaussian Splatting and Dynamic Neural Surface for Mon
        41026, -- 2412.03911 Multi-View Pose-Agnostic Change Localization with Zero Labels
        41038, -- 2412.04120 CrossSDF: 3D Reconstruction of Thin Structures From Cross-Sections
        41045, -- 2412.04244 GigaHands: A Massive Annotated Dataset of Bimanual Hand Activities
        41081, -- 2412.04463 MegaSaM: Accurate, Fast, and Robust Structure and Motion from Casual D
        41127, -- 2412.04887 Momentum-GS: Momentum Gaussian Self-Distillation for High-Quality Larg
        41149, -- 2412.05256 Extrapolated Urban View Synthesis Benchmark
        41155, -- 2412.05278 Birth and Death of a Rose
        41156, -- 2412.05279 Perturb-and-Revise: Flexible 3D Editing with Generative Trajectories
        41179, -- 2412.05700 Temporally Compressed 3D Gaussian Splatting for Dynamic Scenes
        41200, -- 2412.05994 PIG: Physics-Informed Gaussians as Adaptive Parametric Mesh Representa
        41244, -- 2412.06698 Gen-3Diffusion: Realistic Image-to-3D Generation via 2D & 3D Diffusion
        41250, -- 2412.06767 MAtCha Gaussians: Atlas of Charts for High-Quality Geometry and Photor
        41294, -- 2412.07293 EventSplat: 3D Gaussian Splatting from Moving Event Cameras for Real-t
        41312, -- 2412.07660 Proc-GS: Procedural Building Generation for City Assembly with 3D Gaus
        41481, -- 2412.09606 Feat2GS: Probing Visual Foundation Models with Gaussian Splatting
        41482, -- 2412.09608 Representing Long Volumetric Video with Temporal Gaussian Hierarchy
        41626, -- 2412.11525 Sequence Matters: Harnessing Video Models in 3D Super-Resolution
        41631, -- 2412.11586 StrandHead: Text to Strand-Disentangled 3D Head Avatars Using Hair Geo
        41723, -- 2412.12507 3DGUT: Enabling Distorted Cameras and Secondary Rays in Gaussian Splat
        41785, -- 2412.13188 StreetCrafter: Street View Synthesis with Controllable Video Diffusion
        41809, -- 2412.13547 Turbo-GS: Accelerating 3D Gaussian Fitting for High-Quality Radiance F
        41816, -- 2412.13654 GAGS: Granularity-Aware Feature Distillation for Language Gaussian Spl
        41958, -- 2412.15400 SolidGS: Consolidating Gaussian Surfel Splatting for Sparse-View Surfa
        42036, -- 2412.16809 GeoTexDensifier: Geometry-Texture-Aware Densification for High-Quality
        42319, -- 2412.21206 PERSE: Personalized 3D Generative Avatars from A Single Portrait
        42491, -- 2501.02519 Layout2Scene: 3D Semantic Layout Guided Scene Generation via Geometry
        42512, -- 2501.02807 AE-NeRF: Augmenting Event-Based Neural Radiance Fields for Non-ideal C
        42568, -- 2501.03714 MoDec-GS: Global-to-Local Motion Decomposition and Temporal Interval A
        42661, -- 2501.05226 Light Transport-aware Diffusion Posterior Sampling for Single-View Rec
        42781, -- 2501.07104 RMAvatar: Photorealistic Human Avatar Reconstruction from Monocular Vi
        42866, -- 2501.08672 GS-LIVO: Real-Time LiDAR, Inertial, and Visual Multi-sensor Fused Odom
        43001, -- 2501.11043 BF-STVSR: B-Splines and Fourier-Best Friends for High Fidelity Spatial
        43005, -- 2501.11102 RDG-GS: Relative Depth Guidance with Gaussian Splatting for Real-time
        43075, -- 2501.12387 Continuous 3D Perception Model with Persistent State
        43433, -- 2501.18672 Drag Your Gaussian: Effective Drag-Based Editing with Score Distillati
        43459, -- 2501.19084 Laser: Efficient Language-Guided Segmentation in Neural Radiance Field
        44157, -- 2502.09563 Self-Calibrating Gaussian Splatting for Large Field of View Reconstruc
        44485, -- 2502.12894 CAST: Component-Aligned 3D Scene Reconstruction from an RGB Image
        44645, -- 2502.14401 MedFuncta: Modality-Agnostic Representations Based on Efficient Neural
        45092, -- 2502.19441 AniGaussian: Animatable Gaussian Avatar with Pose-guided Deformation
        45218, -- 2502.21001 Towards Lossless Implicit Neural Representation via Bit Plane Decompos
        45490, -- 2503.03511 NeuGrasp: Generalizable Neural Surface Reconstruction with Background
        45507, -- 2503.03751 GEN3C: 3D-Informed World-Consistent Video Generation with Precise Came
        45628, -- 2503.05638 TrajectoryCrafter: Redirecting Camera Trajectory for Monocular Videos
        45724, -- 2503.06740 D3DR: Lighting-Aware Object Insertion in Gaussian Splatting
        45728, -- 2503.06762 Gaussian RBFNet: Gaussian Radial Basis Functions for Fast and Accurate
        45795, -- 2503.07476 SOGS: Second-Order Anchor for Advanced 3D Gaussian Splatting
        45844, -- 2503.08071 GigaSLAM: Large-Scale Monocular SLAM with Hierarchical Gaussian Splats
        45856, -- 2503.08224 HRAvatar: High-Quality and Relightable Gaussian Head Avatar
        45969, -- 2503.09447 Online Language Splatting
        46030, -- 2503.10286 VicaSplat: A Single Run is All You Need for 3D Gaussian Splatting and
        46108, -- 2503.10860 RI3D: Few-Shot Gaussian Splatting With Repair and Inpainting Diffusion
        46128, -- 2503.11172 Uncertainty-Aware Normal-Guided Gaussian Splatting for Surface Reconst
        46206, -- 2503.12553 Niagara: Normal-Integrated Geometric Affine Field for Scene Reconstruc
        46268, -- 2503.13435 WideRange4D: Enabling High-Quality 4D Reconstruction with Wide-Range M
        46278, -- 2503.13588 Next-Scale Autoregressive Models are Zero-Shot Single-Image Object Vie
        46295, -- 2503.13948 Light4GS: Lightweight Compact 4D Gaussian Splatting Generation via Con
        46345, -- 2503.14489 Stable Virtual Camera: Generative View Synthesis with Diffusion Models
        46429, -- 2503.15855 VideoRFSplat: Direct Scene-Level Text-to-3D Gaussian Splatting Generat
        46482, -- 2503.16396 SV4D 2.0: Enhancing Spatio-Temporal Consistency in Multi-View Video Di
        46492, -- 2503.16422 1000+ FPS 4D Gaussian Splatting for Dynamic Scene Rendering
        46524, -- 2503.16924 Optimized Minimal 3D Gaussian Splatting
        46534, -- 2503.17032 TaoAvatar: Real-Time Lifelike Full-Body Talking Avatars for Augmented
        46562, -- 2503.17486 ProtoGS: Efficient and High-Quality Rendering with 3D Gaussian Prototy
        46585, -- 2503.17856 ClaraVid: A Holistic Scene Reconstruction Benchmark From Aerial Perspe
        46607, -- 2503.18073 PanopticSplatting: End-to-End Panoptic Gaussian Splatting
        46695, -- 2503.19232 HoGS: Unified Near and Far Object Reconstruction via Homogeneous Gauss
        46775, -- 2503.20221 TC-GS: Tri-plane based compression for 3D Gaussian Splatting
        46853, -- 2503.21507 F-INR: Functional Tensor Decomposition for Implicit Neural Representat
        46940, -- 2503.22537 LIM: Large Interpolator Model for Dynamic Reconstruction
        46989, -- 2503.23162 NeuralGS: Bridging Neural Fields and 3D Gaussian Splatting for Compact
        47144, -- 2504.01204 Articulated Kinematics Distillation from Video Diffusion Models
        47193, -- 2504.02045 WorldPrompter: Traversable Text-to-Scene Generation
        47586, -- 2504.09048 BlockGaussian: Efficient Large-Scale Scene Novel View Synthesis via Ad
        47798, -- 2504.12292 SHeaP: Self-Supervised Head Geometry Predictor Learned via 2D Gaussian
        47871, -- 2504.13167 ODHSR: Online Dense 3D Reconstruction of Humans and Scenes from Monocu
        47918, -- 2504.13995 Scaling LLaNA: Advancing NeRF-Language Understanding Through Large-Sca
        48009, -- 2504.15278 DRAWER: Digital Reconstruction and Articulation With Environment Reali
        48322, -- 2505.00704 Controllable Weather Synthesis and Removal with Video Diffusion Models
        48358, -- 2505.01838 MVHumanNet++: A Large-scale Dataset of Multi-view Daily Dressing Human
        48478, -- 2505.04262 Bridging Geometry-Coherent Text-to-3D Generation with Multi-View Diffu
        48519, -- 2505.05022 SOAP: Style-Omniscient Animatable Portraits
        48546, -- 2505.05474 3D Scene Generation: A Survey
        48552, -- 2505.05587 Steepest Descent Density Control for Compact 3D Gaussian Splatting
        48562, -- 2505.05848 RefRef: A Synthetic Dataset and Benchmark for Reconstructing Refractiv
        49036, -- 2505.13215 Hybrid 3D-4D Gaussian Splatting for Fast Dynamic Scene Representation
        49069, -- 2505.13440 Recollection from Pensieve: Novel View Synthesis via Learning from Unc
        49096, -- 2505.13817 InstanceBEV: Unifying Instance and BEV Representation for Global Model
        49269, -- 2505.15185 MonoSplat: Generalizable 3D Gaussian Splatting from Monocular Depth Fo
        49319, -- 2505.15737 RUSplatting: Robust 3D Gaussian Splatting for Sparse-View Underwater S
        49690, -- 2505.19138 Veta-GS: View-dependent deformable 3D Gaussian Splatting for thermal i
        49697, -- 2505.19175 Triangle Splatting for Real-Time Radiance Field Rendering
        49910, -- 2505.20897 Cross from Left to Right Brain: Adaptive Text Dreamer for Vision-and-L
        50048, -- 2505.22859 4DTAM: Non-Rigid Tracking and Mapping via Dynamic Surface Gaussians
        50140, -- 2505.23716 AnySplat: Feed-forward 3D Gaussian Splatting from Unconstrained Views
        50470, -- 2506.02751 RobustSplat: Decoupling Densification and Dynamics for Transient-Free
        50554, -- 2506.04115 Multi-view Surface Reconstruction Using Normal and Reflectance Cues
        50795, -- 2506.07932 Squeeze3D: Your 3D Generation Model is Secretly an Extreme Neural Comp
        50994, -- 2506.10335 PointGS: Point Attention-Aware Sparse View Synthesis with Gaussian Spl
        51050, -- 2506.10973 Principled Approaches for Extending Neural Architectures to Function S
        51062, -- 2506.11139 Grids Often Outperform Implicit Neural Representations
        51281, -- 2506.16012 DualTHOR: A Dual-Arm Humanoid Simulation Platform for Contingency-Awar
        51568, -- 2506.22973 Confident Splatting: Confidence-Based Compression of 3D Gaussian Splat
        51653, -- 2507.02705 SIU3R: Simultaneous Scene Understanding and 3D Reconstruction Beyond F
        51757, -- 2507.06109 LighthouseGS: Indoor Structure-aware 3D Gaussian Splatting for Panoram
        51815, -- 2507.07519 MUVOD: A Novel Multi-view Video Object Segmentation Dataset and A Benc
        51848, -- 2507.08776 CLiFT: Compressive Light-Field Tokens for Compute-Efficient and Adapti
        51976, -- 2507.13985 DreamScene: 3D Gaussian-based End-to-end Text-to-3D Scene Generation
        52027, -- 2507.16535 EarthCrafter: Scalable 3D Earth Generation via Dual-Sparse Latent Diff
        52090, -- 2507.21045 Reconstructing 4D Spatial Intelligence: A Survey
        52125, -- 2507.23374 NeRF Is a Valuable Assistant for 3D Gaussian Splatting
        52239, -- 2508.04326 Radiance Fields in XR: A Survey on How Radiance Fields are Envisioned
        52286, -- 2508.06494 LightSwitch: Multi-view Relighting with Material-guided Diffusion
        52435, -- 2508.14037 Distilled-3DGS:Distilled 3D Gaussian Splatting
        52436, -- 2508.14041 LongSplat: Robust Unposed 3D Gaussian Splatting for Casual Long Videos
        52504, -- 2508.17811 MeshSplat: Generalizable Sparse-View Surface Reconstruction via Gaussi
        52668, -- 2509.05263 LatticeWorld: A Multimodal Large Language Model-Empowered Framework fo
        52857, -- 2509.15130 WorldForge: Unlocking Emergent 3D/4D Generation in Video Diffusion Mod
        52942, -- 2509.17083 HyRF: Hybrid Radiance Fields for Memory-efficient and High-quality Nov
        52946, -- 2509.18090 GeoSVR: Taming Sparse Voxels for Geometrically Accurate Surface Recons
        53021, -- 2509.25191 VGGT-X: When VGGT Meets Dense Novel View Synthesis
        53136, -- 2510.02314 StealthAttack: Robust 3D Gaussian Splatting Poisoning via Density-Guid
        53367, -- 2510.08551 ARTDECO: Towards Efficient and High-Fidelity On-the-Fly 3D Reconstruct
        53398, -- 2510.08271 SViM3D: Stable Video Material Diffusion for Single Image 3D Generation
        53623, -- 2510.13454 VIST3A: Text-to-3D by Stitching a Multi-view Reconstruction Network to
        53639, -- 2510.06694 SCas4D: Structural Cascaded Optimization for Boosting Persistent 4D No
        53647, -- 2510.15869 Skyfall-GS: Synthesizing Immersive 3D Urban Scenes from Satellite Imag
        54496, -- 2512.01822 InnoGym: Benchmarking the Innovation Potential of AI Agents
        54572, -- 2512.05113 Splannequin: Freezing Monocular Mannequin-Challenge Footage with Dual-
        54627, -- 2512.07834 Voxify3D: Pixel Art Meets Volumetric Rendering
        54657, -- 2512.08478 Visionary: The World Model Carrier Built on WebGPU-Powered Gaussian Sp
        54697, -- 2512.05446 TED-4DGS: Temporally Activated and Embedding-based Deformation for 4DG
        54716, -- 2512.10959 StereoSpace: Depth-Free Synthesis of Stereo Geometry via End-to-End Di
        55173, -- 2601.04754 ProFuse: Efficient Cross-View Context Fusion for Open-Vocabulary 3D Ga
        55294, -- 2601.09575 OpenVoxel: Training-Free Grouping and Captioning Voxels for Open-Vocab
        55362, -- 2601.11514 ShapeR: Robust Conditional 3D Shape Generation from Casual Captures
        55432, -- 2601.14256 Implicit Neural Representation Facilitates Unified Universal Vision En
        56255, -- 2602.20160 tttLRM: Test-Time Training for Long Context and Autoregressive 3D Reco
        56315, -- 2602.20933 Dropping Anchor and Spherical Harmonics for Sparse-view Gaussian Splat
        56914, -- 2603.17735 TAPESTRY: From Geometry to Appearance via Consistent Turntable Videos
        56930, -- 2603.21304 F4Splat: Feed-Forward Predictive Densification for Feed-Forward 3D Gau
        57461, -- 2604.12626 Habitat-GS: A High-Fidelity Navigation Simulator with Dynamic Gaussian
        57481, -- 2604.11211 3DTV: A Feedforward Interpolation Network for Real-Time View Synthesis
        58334, -- 2604.09835 F3G-Avatar : Face Focused Full-body Gaussian Avatar
        58518, -- 2506.02794 PhysGaia: A Physics-Aware Benchmark with Multi-Body Interactions for D
        58663, -- 2604.00928 Autoregressive Appearance Prediction for 3D Gaussian Avatars
        58728, -- 2603.29296 MotionScale: Reconstructing Appearance, Geometry, and Motion of Dynami
        58907, -- 2603.25129 AirSplat: Alignment and Rating for Robust Feed-Forward 3D Gaussian Spl
        59007, -- 2603.22572 FullCircle: Effortless 3D Reconstruction from Casual 360^circ Captures
        59055, -- 2603.21436 PAS3R: Pose-Adaptive Streaming 3D Reconstruction for Long Video Sequen
        59990, -- 2603.03482 Beyond Pixel Histories: World Models with Persistent 3D State
        60254, -- 2602.22571 GIFSplat: Generative Prior-Guided Iterative Feed-Forward 3D Gaussian S
        60549, -- 2602.16950 HS-3D-NeRF: 3D Surface and Hyperspectral Reconstruction From Stationar
        61260, -- 2602.04317 JOintGS: Joint Optimization of Cameras, Bodies and 3D Gaussians for In
        61268, -- 2602.04251 Towards Next-Generation SLAM: A Survey on 3DGS-SLAM Focusing on Perfor
        61414, -- 2602.02354 Implicit neural representation of textures
        61439, -- 2602.02000 SurfSplat: Conquering Feedforward 2D Gaussian Splatting with Surface C
        61686, -- 2601.23065 EAG-PT: Emission-Aware Gaussians and Path Tracing for Indoor Scene Rec
        62071, -- 2601.17835 Geometry-Grounded Gaussian Splatting
        63177, -- 2512.24763 UniC-Lift: Unified 3D Instance Segmentation via Contrastive Learning
        63390, -- 2512.20377 SmartSplat: Feature-Smart Gaussians for Scalable Compression of Ultra-
        63470, -- 2512.18692 EcoSplat: Efficiency-controllable Feed-forward 3D Gaussian Splatting f
        63620, -- 2512.15126 3DProxyImg: Controllable 3D-Aware Animation Synthesis from Single Imag
        63682, -- 2512.13796 Nexels: Neurally-Textured Surfels for Real-Time Novel View Synthesis w
        63748, -- 2512.12534 Animus3D: Text-driven 3D Animation via Motion Score Distillation
        63752, -- 2512.12430 Endless World: Real-Time 3D-Aware Long Video Generation
        63812, -- 2512.10947 Towards Efficient and Effective Multi-Camera Encoding for End-to-End D
        63816, -- 2512.10940 OmniView: An All-Seeing Diffusion Model for 3D and 4D View Synthesis
        63857, -- 2512.10267 Long-LRM++: Preserving Fine Details in Feed-Forward Wide-Coverage Reco
        63875, -- 2512.09923 Splatent: Splatting Diffusion Latents for Novel View Synthesis
        63900, -- 2512.15742 SHARe-KAN: Holographic Vector Quantization for Memory-Bound Inference
        63901, -- 2512.09278 LoGoColor: Local-Global 3D Colorization for 360° Scenes
        63908, -- 2512.09162 GTAvatar: Bridging Gaussian Splatting and Texture Mapping for Relighta
        63914, -- 2512.08930 Selfi: Self Improving Reconstruction Engine via 3D Geometric Feature A
        64045, -- 2512.06438 AGORA: Adversarial Generation Of Real-time Animatable 3D Gaussian Head
        64107, -- 2512.04830 FreeGen: Feed-Forward Reconstruction-Generation Co-Training for Free-V
        64110, -- 2512.04786 LaFiTe: A Generative Latent Field for 3D Native Texturing
        64300, -- 2512.01306 Gaussian Swaying: Surface-Based Framework for Aerodynamic Simulation w
        64302, -- 2512.01296 EGG-Fusion: Efficient 3D Reconstruction with Geometry-aware Gaussian S
        64434, -- 2511.22233 IE-SRGS: An Internal-External Knowledge Fusion Framework for High-Fide
        64505, -- 2511.20924 GaINeR: Geometry-Aware Implicit Network Representation
        64536, -- 2511.20343 AMB3R: Accurate Feed-forward Metric-scale 3D Reconstruction with Backe
        64641, -- 2511.18680 Inverse Rendering for High-Genus Surface Meshes from Multi-View Images
        64665, -- 2511.18517 Foundations of Artificial Intelligence Frameworks: Notion and Limits o
        64675, -- 2511.18387 Scaling Implicit Fields via Hypernetwork-Driven Multiscale Coordinate
        64709, -- 2511.17932 Novel View Synthesis from A Few Glimpses via Test-Time Natural Video C
        64730, -- 2511.17364 SVRecon: Sparse Voxel Rasterization for Surface Reconstruction
        64956, -- 2511.12614 OPFormer: Object Pose Estimation leveraging foundation model with geom
        65220, -- 2511.07321 YoNoSplat: You Only Need One Model for Feedforward 3D Gaussian Splatti
        65253, -- 2511.06765 Robust and High-Fidelity 3D Gaussian Splatting: Fusing Pose Priors and
        65775, -- 2510.23880 TRELLISWorld: Training-Free World Generation from Object Generators
        66120, -- 2510.18253 OpenInsGaussian: Open-vocabulary Instance Gaussian Segmentation with C
        66414, -- 2510.12971 Actron3D: Learning Actionable Neural Functions from Videos for Transfe
        66473, -- 2510.11878 GS-Verse: Mesh-based Gaussian Splatting for Physics-aware Interaction
        66703, -- 2510.08491 Splat the Net: Radiance Fields with Splattable Neural Primitives
        67037, -- 2510.03104 Geometry Meets Vision: Revisiting Pretrained Semantics in Distilled Fi
        68038, -- 2509.17246 SPFSplatV2: Efficient Self-Supervised Pose-Free 3D Gaussian Splatting
        68064, -- 2509.16873 M^3VIR: A Large-Scale Multi-Modality Multi-View Synthesized Benchmark
        68114, -- 2509.16336 Neural Atlas Graphs for Dynamic Scene Decomposition and Editing
        68136, -- 2509.15892 MoAngelo: Motion-Aware Neural Surface Reconstruction for Dynamic Scene
        68252, -- 2509.14191 MCGS-SLAM: A Multi-Camera SLAM Framework Using Gaussian Splatting for
        68423, -- 2509.11185 SAMP: Spatial Anchor-based Motion Policy for Collision-Aware Robotic M
        68503, -- 2509.09143 Objectness Similarity: Capturing Object-Level Fidelity in 3D Scene Eva
        68567, -- 2509.07782 RayGaussX: Accelerating Gaussian-Based Ray Marching for Real-Time and
        68583, -- 2509.07493 Accurate and Complete Surface Reconstruction from 3D Gaussians via Dir
        68660, -- 2509.07021 MEGS^{2}: Memory-Efficient Gaussian Splatting via Spherical Gaussians
        68694, -- 2509.05131 A Scalable Attention-Based Approach for Image-to-3D Texture Mapping
        68923, -- 2509.00800 SWAGSplatting: Semantic-guided Water-scene Augmented Gaussian Splattin
        69101, -- 2508.19754 FastAvatar: Towards Unified Fast High-Fidelity 3D Avatar Reconstructio
        69105, -- 2508.19699 LabelGS: Label-Aware 3D Gaussian Splatting for 3D Scene Segmentation
        69469, -- 2508.13792 VisionLaw: Inferring Interpretable Intrinsic Dynamics from Visual Obse
        69620, -- 2508.11431 Remove360: Benchmarking Residuals After Object Removal in 3D Gaussian
        69703, -- 2412.00578 Speedy-Splat: Fast 3D Gaussian Splatting with Sparse Pixels and Sparse
        69856, -- 2508.08048 S^2VG: 3D Stereoscopic and Spatial Video Generation via Denoising Fram
        69897, -- 2508.07557 Splat4D: Diffusion-Enhanced 4D Gaussian Splatting for Temporally and S
        70043, -- 2508.05343 3DGabSplat: 3D Gabor Splatting for Frequency-adaptive Radiance Field R
        70068, -- 2508.05064 A Study of the Framework and Real-World Applications of Language Embed
        70109, -- 2508.04508 Surf3R: Rapid Surface Reconstruction from Sparse RGB Views in Seconds
        70110, -- 2508.04505 MonoCloth: Reconstruction and Animation of Cloth-Decoupled Human Avata
        70147, -- 2508.04099 DET-GS: Depth- and Edge-Aware Regularization for High-Fidelity 3D Gaus
        70149, -- 2508.04090 Bridging Diffusion Models and 3D Representations: A 3D Consistent Supe
        70219, -- 2508.03180 Duplex-GS: Proxy-Guided Weighted Blending for Real-Time Order-Independ
        70262, -- 2508.02493 Low-Frequency First: Eliminating Floating Artifacts in 3D Gaussian Spl
        70509, -- 2507.23162 Neural Multi-View Self-Calibrated Photometric Stereo without Photometr
        70517, -- 2507.23006 Robust and Efficient 3D Gaussian Splatting for Urban Scene Reconstruct
        70550, -- 2507.22412 UAVScenes: A Multi-Modal Dataset for UAVs
        70712, -- 2507.19481 HairCUP: Hair Compositional Universal Prior for 3D Gaussian Avatars
        70783, -- 2507.18255 LONG3R: Long Sequence Streaming 3D Reconstruction
        70784, -- 2507.18231 PS-GS: Gaussian Splatting for Multi-View Photometric Stereo
        70797, -- 2507.18023 High-fidelity 3D Gaussian Inpainting: preserving multi-view consistenc
        70887, -- 2507.16406 Sparse-View 3D Reconstruction: Recent Advances and Open Challenges
        71056, -- 2507.12667 VolSegGS: Segmentation and Tracking in Dynamic Volumetric Scenes via D
        71058, -- 2507.12646 Reconstruct, Inpaint, Finetune: Dynamic Novel-view Synthesis from Mono
        71060, -- 2507.12621 NLI4VolVis: Natural Language Interaction for Volume Visualization via
        71087, -- 2507.11971 HPR3D: Hierarchical Proxy Representation for High-Fidelity 3D Reconstr
        71311, -- 2507.06719 A Neural Representation Framework with LLM-Driven Spatial Reasoning fo
        71426, -- 2507.04004 Gaussian-LIC2: LiDAR-Inertial-Camera Gaussian Splatting SLAM
        71438, -- 2507.03737 Outdoor Monocular SLAM with Global Scale-Consistent 3D Gaussian Pointm
        71484, -- 2507.02419 AvatarMakeup: Realistic Makeup Transfer for 3D Animatable Head Avatars
        71488, -- 2507.02363 LocalDyGS: Multi-view Global Dynamic Scene Modeling via Adaptive Local
        71580, -- 2507.00363 GDGS: 3D Gaussian Splatting Via Geometry-Guided Initialization And Dyn
        71621, -- 2506.23611 AttentionGS: Towards Initialization-Free 3D Gaussian Splatting via Str
        71709, -- 2506.21478 SmoothSinger: A Conditional Diffusion Model for Singing Voice Synthesi
        71923, -- 2506.14742 SyncTalk++: High-Fidelity and Efficient Synchronized Talking Heads Syn
        72044, -- 2506.10507 Edit360: 2D Image Edits to 3D Assets from Any Angle
        72126, -- 2506.07698 NOVA3D: Normal Aligned Video Diffusion Model for Single Image to 3D Ge
        72236, -- 2506.05347 Neural Inverse Rendering from Propagating Light
        72271, -- 2506.04174 FlexGS: Train Once, Deploy Everywhere with Many-in-One Flexible 3D Gau
        72536, -- 2505.23642 Radiant Triangle Soup with Soft Connectivity Forces for 3D Reconstruct
        73005, -- 2505.11992 SpatialCrafter: Unleashing the Imagination of Video Diffusion Models f
        73057, -- 2505.10473 ControlGS: Consistent Structural Compression Control for Deployment-Aw
        73238, -- 2504.21778 LoC-LIC: Low Complexity Learned Image Coding Using Hierarchical Featur
        73373, -- 2504.16693 PIN-WM: Learning Physics-INformed World Models for Non-Prehensile Mani
        73409, -- 2504.15835 Text-based Animatable 3D Avatars with Morphable Model Alignment
        73482, -- 2504.11893 CAGS: Open-Vocabulary 3D Scene Understanding with Context-Aware Gaussi
        73489, -- 2504.13204 EDGS: Eliminating Densification for Efficient Convergence of 3DGS
        73536, -- 2504.09588 TextSplat: Text-Guided Semantic Fusion for Generalizable Gaussian Spla
        73541, -- 2504.09491 DropoutGS: Dropping Out Gaussians for Better Sparse-view Rendering
        73571, -- 2504.08252 Stereophotoclinometry Revisited
        73625, -- 2504.07144 GIGA: Generalizable Sparse Image-driven Gaussian Humans
        73631, -- 2504.06178 Flash Sculptor: Modular 3D Worlds from Objects
        74034, -- 2503.12947 DivCon-NeRF: Diverse and Consistent Ray Augmentation for Few-Shot NeRF
        74063, -- 2503.12307 Swift4D:Adaptive divide-and-conquer Gaussian Splatting for compact and
        74066, -- 2503.12284 REdiSplats: Ray Tracing for Editable Gaussian Splatting
        74109, -- 2503.10256 ROODI: Reconstructing Occluded Objects with Denoising Inpainters
        74111, -- 2503.10170 GS-SDF: LiDAR-Augmented Gaussian Splatting and Neural SDF for Geometri
        74112, -- 2503.10143 GaussHDR: High Dynamic Range Gaussian Splatting via Learning Unified 3
        74165, -- 2503.08217 S3R-GS: Streamlining the Pipeline for Large-Scale Street Scene Reconst
        74171, -- 2503.08135 ArticulatedGS: Self-supervised Digital Twin Modeling of Articulated Ob
        74239, -- 2503.05082 Taming Video Diffusion Prior with Scene-Grounding Guidance for 3D Gaus
        74372, -- 2503.00370 Scalable Real2Sim: Physics-Aware Asset Generation Via Robotic Pick-and
        74412, -- 2502.20669 EndoPBR: Material and Lighting Estimation for Photorealistic Surgical
        74437, -- 2502.19800 TrackGS: Optimizing COLMAP-Free 3D Gaussian Splatting with Global Trac
        74478, -- 2502.18219 Synthesizing Consistent Novel Views via 3D Epipolar Attention without
        74925, -- 2502.02091 Instruct-4DGS: Efficient Dynamic Scene Editing via 4D Gaussian-based S
        74960, -- 2502.01157 Radiant Foam: Real-Time Differentiable Ray Tracing
        75062, -- 2501.18630 Deformable Beta Splatting
        75096, -- 2501.14231 Micro-macro Wavelet-based Gaussian Splatting for 3D Reconstruction fro
        75155, -- 2501.10788 Decoupling Appearance Variations with 3D Consistent Features in Gaussi
        75182, -- 2501.08982 CityLoc: 6DoF Pose Distributional Localization for Text Descriptions i
        75289, -- 2501.02725 Advances in Artificial Intelligence: A Review for the Creative Industr
        75337, -- 2412.20720 4D Gaussian Splatting: Modeling Dynamic Scenes with Native 4D Primitiv
        75457, -- 2412.11762 GS-ProCams: Gaussian Splatting-based Projector-Camera Systems
        75566, -- 2412.05548 Street Gaussians without 3D Object Tracker
        75585, -- 2412.04459 Sparse Voxels Rasterization: Real-time High-fidelity Radiance Field Re
        75699, -- 2411.17235 MLI-NeRF: Multi-Light Intrinsic-Aware Neural Radiance Fields
        75706, -- 2411.16816 SplatAD: Real-Time Lidar and Camera Rendering with 3D Gaussian Splatti
        75843, -- 2411.04810 GANESH: Generalizable NeRF for Lensless Imaging
        75926, -- 2410.21955 ActiveSplat: High-Fidelity Scene Reconstruction through Active Gaussia
        76019, -- 2410.13613 MEGA: Memory-Efficient 4D Gaussian Splatting for Dynamic Scenes
        76028, -- 2410.13271 Inductive Gradient Adjustment For Spectral Bias In Implicit Neural Rep
        76070, -- 2410.09771 EUGens: Efficient, Unified, and General Dense Layers
        76143, -- 2410.05050 FreSh: Frequency Shifting for Accelerated Neural Representation Learni
        76753, -- 2407.11419 TeethDreamer: 3D Teeth Reconstruction from Five Intra-oral Photographs
        76817, -- 2407.02945 VEGS: View Extrapolation of Urban Scenes in 3D Gaussian Splatting usin
        76866, -- 2407.00435 RTGS: Enabling Real-Time Gaussian Splatting on Mobile Devices Using Ef
        76922, -- 2406.15643 Taming 3DGS: High-Quality Radiance Fields with Limited Resources
        76984, -- 2406.11077 Learning Relighting and Intrinsic Decomposition in Neural Radiance Fie
        77264, -- 2405.10255 When LLMs step into the 3D World: A Survey and Meta-Analysis of 3D Tas
        77383, -- 2404.14967 CoARF: Controllable 3D Artistic Style Transfer for Radiance Fields
        77388, -- 2404.14674 HOIN: High-Order Implicit Neural Representations
        77393, -- 2404.13921 NeRF-DetS: Enhanced Adaptive Spatial-wise Sampling and View-wise Fusio
        77419, -- 2404.11358 DeblurGS: Gaussian Splatting for Camera Motion Blur
        77426, -- 2404.10272 Plug-and-Play Acceleration of Occupancy Grid-based NeRF Rendering usin
        77428, -- 2404.10394 Portrait3D: Text-Guided High-Quality 3D Portrait Generation Using Pyra
        77448, -- 2404.07993 Connecting NeRFs, Images, and Text
        77468, -- 2404.06926 Gaussian-LIC: Real-Time Photo-Realistic SLAM with Gaussian Splatting a
        77757, -- 2402.16308 DreamUp3D: Object-Centric Generative Models for Single-View 3D Scene U
        77788, -- 2402.12886 Real-time High-resolution View Synthesis of Complex Scenes with Explic
        77956, -- 2401.07402 Improved Implicit Neural Representation with Fourier Reparameterized T
        78058, -- 2312.13277 Deep Learning on Object-centric 3D Neural Fields
        78106, -- 2312.08012 uSF: Learning Neural Semantic Field with Uncertainty
        78164, -- 2312.01632 GaussianHead: High-fidelity Head Avatars with Learnable Gaussian Deriv
        78186, -- 2311.17350 Implicit-explicit Integrated Representations for Multi-view Video Comp
        78220, -- 2311.12897 An Efficient 3D Gaussian Representation for Monocular/Multi-view Dynam
        78491, -- 2309.12790 NTO3D: Neural Target Object 3D Reconstruction with Segment Anything
        78538, -- 2309.05448 Panoptic Vision-Language Feature Fields
        78603, -- 2308.14737 Flexible Techniques for Differentiable Rendering with 3D Gaussians
        79180, -- 2304.03117 DreamFace: Progressive Generation of Animatable 3D Faces under Text Gu
        79223, -- 2303.10962 Neural Implicit Vision-Language Feature Fields
        79230, -- 2303.10340 3D Data Augmentation for Driving Scenes on Camera
        79533, -- 2211.13969 Unsupervised Continual Semantic Adaptation through Neural Rendering
        79730, -- 2209.09050 Loc-NeRF: Monte Carlo Localization using Neural Radiance Fields
        79929, -- 2206.01178 Discretization Invariant Networks for Learning Maps between Neural Fie
        83465, -- 2605.20150 TideGS: Scalable Training of Over One Billion 3D Gaussian Splatting Pr
        83989, -- 2503.09750 SASNet: Spatially-Adaptive Sinusoidal Networks for INRs
        84020, -- 2505.20270 ParticleGS: Learning Neural Gaussian Particle Dynamics from Videos for
        84108, -- 2509.22615 GaussianVision: Vision-Language Alignment from Compressed Image Repres
        84131, -- 2510.16410 REALM: An MLLM-Agent Framework for Open World 3D Reasoning Segmentatio
        84165, -- 2511.12370 Changes in Real Time: Online Scene Change Detection with Multi-View Fu
        84188, -- 2511.15487 NTK-Guided Implicit Neural Teaching
        84222, -- 2511.18794 ChronoGS: Disentangling Invariants and Changes in Multi-Period Scenes
        84232, -- 2511.19172 MetroGS: Efficient and Stable Reconstruction of Geometrically Accurate
        84257, -- 2511.21113 FaithFusion: Harmonizing Reconstruction and Generation via Pixel-wise
        84271, -- 2511.22147 RemedyGS: Defend 3D Gaussian Splatting Against Computation Cost Attack
        84303, -- 2512.01329 TagSplat: Topology-Aware Gaussian Splatting for Dynamic Mesh Modeling
        84311, -- 2512.02341 TALO: Pushing 3D Vision Foundation Models Towards Globally Consistent
        84337, -- 2512.04076 Radiance Meshes for Volumetric Reconstruction
        84359, -- 2512.06684 EMGauss: Continuous Slice-to-3D Reconstruction via Dynamic Gaussian Mo
        84399, -- 2512.14126 Consistent Instance Field for Dynamic Scene Understanding
        84406, -- 2512.15508 Off The Grid: Detection of Primitives for Feed-Forward 3D Gaussian Spl
        84416, -- 2512.16811 GeoPredict: Leveraging Predictive Kinematics and 3D Gaussian Geometry
        84456, -- 2601.02141 Efficient Unrolled Networks for Large-Scale 3D Inverse Problems
        84473, -- 2601.09265 GaussianFluent: Gaussian Simulation for Dynamic Scenes with Mixed Mate
        84475, -- 2601.09665 SCE-SLAM: Scale-Consistent Monocular SLAM via Scene Coordinate Embeddi
        84477, -- 2601.10200 ELITE: Efficient Gaussian Head Avatar from a Monocular Video via Learn
        84493, -- 2601.17900 Revisiting 3D Reconstruction Kernels as Low-Pass Filters
        84509, -- 2602.09999 Faster-GS: Analyzing and Improving Gaussian Splatting Optimization
        84591, -- 2602.21105 BrepGaussian: CAD reconstruction from Multi-View Images with Gaussian
        84622, -- 2602.22376 AeroDGS: Physically Consistent Dynamic Gaussian Splatting for Single-S
        84625, -- 2602.22625 DiffBMP: Differentiable Rendering with Bitmap Primitives
        84644, -- 2602.23574 Evidential Neural Radiance Fields
        84675, -- 2603.00805 NERFIFY: A Multi-Agent Framework for Turning NeRF Papers into Code
        84684, -- 2603.01028 Content-Aware Frequency Encoding for Implicit Neural Representations w
        84692, -- 2603.01194 RnG: A Unified Transformer for Complete 3D Modeling from Partial Obser
        84720, -- 2603.02893 Intrinsic Geometry-Appearance Consistency Optimization for Sparse-View
        84804, -- 2603.07789 SGI: Structured 2D Gaussians for Efficient and Compact Large Image Rep
        84868, -- 2603.12078 Node-RF: Learning Generalized Continuous Space-Time Scene Dynamics wit
        84883, -- 2603.12903 Spectral-Geometric Neural Fields for Pose-Free LiDAR View Synthesis
        84937, -- 2603.16447 ProgressiveAvatars: Progressive Animatable 3D Gaussian Avatars
        84977, -- 2603.19121 CustomTex: High-fidelity Indoor Scene Texturing via Multi-Reference Cu
        84987, -- 2603.19682 3D Gaussian Splatting with Self-Constrained Priors for High Fidelity S
        85002, -- 2603.20448 Thermal is Always Wild: Characterizing and Addressing Challenges in Th
        85018, -- 2603.21055 SGAD-SLAM: Splatting Gaussians at Adjusted Depth for Better Radiance F
        85152, -- 2603.26810 Unblur-SLAM: Dense Neural SLAM for Blurry Inputs
        85160, -- 2603.27151 DiffSoup: Direct Differentiable Rasterization of Triangle Soup for Ext
        85165, -- 2603.27228 NimbusGS: Unified 3D Scene Reconstruction under Hybrid Weather
        85174, -- 2603.27516 SGS-Intrinsic: Semantic-Invariant Gaussian Splatting for Sparse-View I
        85222, -- 2604.00648 DirectFisheye-GS: Enabling Native Fisheye Input in Gaussian Splatting
        85232, -- 2604.01561 ReFlow: Self-correction Motion Learning for Dynamic Scene Reconstructi
        85246, -- 2604.02331 EventHub: Data Factory for Generalizable Event-Based Stereo Networks w
        85254, -- 2604.02915 GP-4DGS: Probabilistic 4D Gaussian Splatting from Monocular Video via
        85258, -- 2604.03069 SparseSplat: Towards Applicable Feed-Forward 3D Gaussian Splatting wit
        85269, -- 2604.04063 4C4D: 4 Camera 4D Gaussian Splatting
        85274, -- 2604.04425 HandDreamer: Zero-Shot Text to 3D Hand Model Generation using Correcti
        85295, -- 2604.05794 EfficientMonoHair: Fast Strand-Level Reconstruction from Monocular Vid
        85345, -- 2604.10573 Learning 3D Representations for Spatial Intelligence from Unposed Mult
        85369, -- 2604.12625 Neural Dynamic GI: Random-Access Neural Compression for Temporal Light
        85385, -- 2604.15239 TokenGS: Decoupling 3D Gaussian Prediction from Pixels with Learnable
        85400, -- 2604.16540 PoInit-of-View: Poisoning Initialization of Views Transfers Across Mul
        85442, -- 2604.21631 DualSplat: Robust 3D Gaussian Splatting via Pseudo-Mask Bootstrapping
        85494, -- 2605.01854 High-Fidelity Mobile Avatars with Pruned Local Blendshapes
        85539, -- 2605.10204 3DReflecNet: A Large-Scale Dataset for 3D Reconstruction of Reflective
        85554, -- 2605.13465 Z-Order Transformer for Feed-Forward Gaussian Splatting
        85556, -- 2605.13855 SparseOIT: Improving Order-Independent Transparency 3DGS via Active Se
        85596, -- 2605.22069 TWINGS: Thin Plate Splines Warp-aligned Initialization for Sparse-View
        85730, -- 2510.15736 Fix False Transparency by Noise Guided Splatting
        85898, -- 2505.19154 FHGS: Feature-Homogenized Gaussian Splatting
        85928, -- 2505.16533 Motion Matters: Compact Gaussian Streaming for Free-Viewpoint Video Re
        86224, -- 2501.16312 LinPrim: Linear Primitives for Differentiable Volumetric Rendering
        86275, -- 2506.11252 Anti-Aliased 2D Gaussian Splatting
        86296, -- 2412.12772 Optimize the Unseen - Fast NeRF Cleanup with Free Space Prior
        86347, -- 2510.06046 GLVD: Guided Learned Vertex Descent
        86462, -- 2507.17336 Temporal Smoothness-Aware Rate-Distortion Optimized 4D Gaussian Splatt
        86618, -- 2508.06715 Restage4D: Reanimating Deformable 3D Reconstruction from a Single Vide
        86707, -- 2412.09043 DrivingRecon: Large 4D Gaussian Reconstruction Model For Autonomous Dr
        86725, -- 2510.08279 Learning Neural Exposure Fields for View Synthesis
        86748, -- 2509.20824 ARMesh: Autoregressive Mesh Generation via Next-Level-of-Detail Predic
        86849, -- 2505.21258 Plenodium: UnderWater 3D Scene Reconstruction with Plenoptic Medium Re
        86870, -- 2506.12945 Metropolis-Hastings Sampling for 3D Gaussian Reconstruction
        86893, -- 2507.02863 Point3R: Streaming 3D Reconstruction with Explicit Spatial Pointer Mem
        87057, -- 2505.23280 Holistic Large-Scale Scene Reconstruction via Mixed Gaussian Splatting
        87551, -- 2503.18438 ReconDreamer++: Harmonizing Generative and Reconstructive Models for D
        87562, -- 2412.07494 ResGS: Residual Densification of 3D Gaussian for Efficient Detail Reco
        87580, -- 2505.23044 SpatialSplat: Efficient Semantic 3D from Sparse Unposed Images
        87613, -- 2504.09129 A Constrained Optimization Approach for Gaussian Splatting from Coarse
        87647, -- 2503.14786 SketchSplat: 3D Edge Reconstruction via Differentiable Multi-view Sket
        87668, -- 2412.12765 Monocular Facial Appearance Capture in the Wild
        87691, -- 2509.17430 EmbodiedSplat: Personalized Real-to-Sim-to-Real Navigation with Gaussi
        87714, -- 2507.09748 Advancing Text-to-3D Generation with Linearized Lookahead Variational
        87715, -- 2502.08377 Not All Frame Features Are Equal: Video-to-4D Generation via Decouplin
        87743, -- 2411.18303 InfiniDreamer: Arbitrarily Long Human Motion Generation via Segment Sc
        87754, -- 2508.05506 MagicHOI: Leveraging 3D Priors for Accurate Hand-object Reconstruction
        87774, -- 2502.17288 GaussianFlowOcc: Sparse and Weakly Supervised Occupancy Estimation usi
        87781, -- 2410.24204 GeoSplatting: Towards Geometry Guided Gaussian Splatting for Physicall
        87823, -- 2411.15582 EMD: Explicit Motion Modeling for High-Quality Street Gaussian Splatti
        87831, -- 2504.07949 InteractAvatar: Modeling Hand-Face Interaction in Photorealistic Avata
        87864, -- 2411.16392 Quadratic Gaussian Splatting: High Quality Surface Reconstruction with
        87869, -- 2507.15602 SurfaceSplat: Connecting Surface Reconstruction and Gaussian Splatting
        87916, -- 2504.10024 Relative Illumination Fields: Learning Medium and Light Independent Un
        87931, -- 2508.09830 RayletDF: Raylet Distance Fields for Generalizable 3D Surface Reconstr
        87939, -- 2412.16919 TAR3D: Creating High-Quality 3D Assets via Next-Part Prediction
        87994, -- 2411.11941 TimeFormer: Capturing Temporal Relationships of Deformable 3D Gaussian
        88033, -- 2501.03399 Compression of 3D Gaussian Splatting with Optimized Feature Planes and
        88059, -- 2506.23854 HiNeuS: High-fidelity Neural Surface Mitigating Low-texture and Reflec
        88090, -- 2411.16768 Sequential Gaussian Avatars with Hierarchical Motion Context
        88093, -- 2504.02817 Efficient Autoregressive Shape Generation via Octree-Based Adaptive To
        88105, -- 2510.01669 UniVerse: Unleashing the Scene Prior of Video Diffusion Models for Rob
        88141, -- 2412.07608 Faster and Better 3D Splatting via Group Training
        88226, -- 2508.06014 ExploreGS: Explorable 3D Scene Reconstruction with Virtual Camera Samp
        88245, -- 2507.20200 Neural Shell Texture Splatting: More Details and Fewer Primitives
        88267, -- 2507.04408 A View-consistent Sampling Method for Regularized Training of Neural R
        88321, -- 2509.19726 PolGS: Polarimetric Gaussian Splatting for Fast Reflective Surface Rec
        88366, -- 2509.10678 T2Bs: Text-to-Character Blendshapes via Video Generation
        88377, -- 2507.18155 GeoAvatar: Adaptive Geometrical Gaussian Splatting for 3D Head Avatar
        88385, -- 2508.12615 WIPES: Wavelet-based Visual Primitives
        88388, -- 2406.18582 CanFields: Consolidating Diffeomorphic Flows for Non-Rigid 4D Interpol
        88420, -- 2506.23479 Instant GaussianImage: A Generalizable and Self-Adaptive Image Represe
        88435, -- 2507.14596 DiSCO-3D : Discovering and Segmenting Sub-Concepts from Open-vocabular
        88452, -- 2504.16606 HUG: Hierarchical Urban Gaussian Splatting with Block-Based Reconstruc
        88462, -- 2411.08508 BillBoard Splatting (BBSplat): Learnable Textured Primitives for Novel
        88478, -- 2505.05591 QuickSplat: Fast 3D Surface Reconstruction via Learned Gaussian Initia
        88489, -- 2506.23518 WAVE: Warp-Based View Guidance for Consistent Novel View Synthesis Usi
        88512, -- 2507.03976 Robust Low-light Scene Restoration via Illumination Transition
        88518, -- 2410.13195 UniGS: Modeling Unitary 3D Gaussians for Novel View Synthesis from Spa
        89187, -- 2411.13525 Geometric Algebra Planes: Convex Implicit Neural Volumes
        89846, -- 2412.01124 SUICA: Learning Super-high Dimensional Sparse Implicit Neural Represen
        89961, -- 2505.24746 Tackling View-Dependent Semantics in 3D Language Gaussian Splatting
        90049, -- 2505.14170 Nonparametric Teaching for Graph Property Learners
        90095, -- 2408.07967 FlashGS: Efficient 3D Gaussian Splatting for Large-scale and High-reso
        90098, -- 2412.10209 GAF: Gaussian Avatar Reconstruction from Monocular Videos via Multi-vi
        90194, -- 2412.12849 HyperGS: Hyperspectral 3D Gaussian Splatting
        90196, -- 2502.11801 3D Gaussian Inpainting with Depth-Guided Cross-View Consistency
        90206, -- 2411.19895 GuardSplat: Efficient and Robust Watermarking for 3D Gaussian Splattin
        90210, -- 2503.18513 LookCloser: Frequency-aware Radiance Field for Tiny-Detail Scene
        90231, -- 2505.18932 Geometry-guided Online 3D Video Synthesis with Multi-View Temporal Con
        90235, -- 2412.16028 CoCoGaussian: Leveraging Circle of Confusion for Gaussian Splatting fr
        90255, -- 2412.10084 ProbeSDF: Light Field Probes For Neural Surface Reconstruction
        90262, -- 2504.19819 Joint Optimization of Neural Radiance Fields and Continuous Camera Mot
        90271, -- 2503.18421 4DGC: Rate-Aware 4D Gaussian Compression for Efficient Streamable Free
        90293, -- 2503.12886 RGBAvatar: Reduced Gaussian Blendshapes for Online Modeling of Head Av
        90316, -- 2503.10148 3D Student Splatting and Scooping
        90319, -- 2505.21335 Structure from Collision
        90320, -- 2412.10153 EVOS: Efficient Implicit Neural Training via EVOlutionary Selector
        90361, -- 2504.06210 HiMoR: Monocular Deformable Gaussian Reconstruction with Hierarchical
        90365, -- 2401.12977 IRIS: Inverse Rendering of Indoor Scenes from Low Dynamic Range Images
        90368, -- 2503.14198 RoGSplat: Learning Robust Generalizable Human Gaussian Splatting from
        90379, -- 2503.19673 MultimodalStudio: A Heterogeneous Sensor Dataset and Framework for Neu
        90384, -- 2411.12592 SPARS3R: Semantic Prior Alignment and Regularization for Sparse 3D Rec
        90415, -- 2410.20723 CompGS: Unleashing 2D Compositionality for Compositional Text-to-3D vi
        90428, -- 2504.20403 Creating Your Editable 3D Photorealistic Avatar with Tetrahedron-const
        90437, -- 2504.07146 VideoSPatS: Video SPatiotemporal Splines for Disentangled Occlusion, A
        90447, -- 2503.17276 HyperNVD: Accelerating Neural Video Decomposition via Hypernetworks
        90457, -- 2502.20387 InsTaG: Learning Personalized 3D Talking Head from Few-Second Video
        90475, -- 2503.16979 Instant Gaussian Stream: Fast and Generalizable Streaming of Dynamic S
        90479, -- 2503.24374 ERUPT: Efficient Rendering with Unposed Patch Transformer
        90480, -- 2503.14029 Rethinking End-to-End 2D to 3D Scene Segmentation in Gaussian Splattin
        90532, -- 2410.08107 IncEventGS: Pose-Free Gaussian Splatting from a Single Event Camera
        90535, -- 2503.18402 DashGaussian: Optimizing 3D Gaussian Splatting in 200 Seconds
        90559, -- 2503.21816 EVPGS: Enhanced View Prior Guidance for Splatting-based Extrapolated V
        90564, -- 2503.18123 End-to-End Implicit Neural Representations for Classification
        90566, -- 2412.20522 MaskGaussian: Adaptive 3D Gaussian Representation from Probabilistic M
        90573, -- 2312.06085 SFDM: Robust Decomposition of Geometry and Reflectance for Realistic F
        90590, -- 2411.18625 Textured Gaussians for Enhanced 3D Scene Appearance Modeling
        90592, -- 2409.02482 Volumetric Surfaces: Representing Fuzzy Geometries with Layered Meshes
        90603, -- 2504.00773 DropGaussian: Structural Regularization for Sparse-view Gaussian Splat
        90615, -- 2505.19793 Depth-Guided Bundle Sampling for Efficient Generalizable Neural Radian
        90621, -- 2501.01601 Few-shot Implicit Function Generation via Equivariance
        90683, -- 2503.19373 DeClotH: Decomposable 3D Cloth and Human Body Reconstruction from a Si
        90698, -- 2504.14967 3D Gaussian Head Avatars with Expressive Dynamic Appearances by Compac
        90710, -- 2503.19458 GaussianUDF: Inferring Unsigned Distance Functions through 3D Gaussian
        90732, -- 2503.18361 NeRFPrior: Learning Neural Radiance Field as a Prior for Indoor Scene
        90736, -- 2412.11752 Deformable Radial Kernel Splatting
        90741, -- 2503.21442 RainyGS: Efficient Rain Synthesis with Physically-Based Gaussian Splat
        90748, -- 2411.17067 Geometry Field Splatting with Gaussian Surfels
        90755, -- 2403.10344 ViiNeuS: Volumetric Initialization for Implicit Neural Surface Reconst
        90766, -- 2503.08352 Mitigating Ambiguities in 3D Classification with Gaussian Splatting
        90776, -- 2411.15482 SplatFlow: Self-Supervised Dynamic Gaussian Splatting in Neural Motion
        90785, -- 2504.20026 LIRM: Large Inverse Rendering Model for Progressive Reconstruction of
        90822, -- 2504.12909 Real-time High-fidelity Gaussian Human Avatars with Position-based Int
        90823, -- 2411.19548 ReconDreamer: Crafting World Models for Driving Scene Reconstruction v
        90859, -- 2502.14454 Exploiting Deblurring Networks for Radiance Fields
        90895, -- 2503.00881 Evolving High-Quality Rendering and Reconstruction in a Unified Framew
        90897, -- 2501.06693 Vid2Sim: Realistic and Interactive Simulation from Video for Urban Nav
        90912, -- 2404.16323 LeanGaussian: Breaking Pixel or Point Cloud Correspondence in Modeling
        90920, -- 2412.03378 Volumetrically Consistent 3D Gaussian Rasterization
        90922, -- 2503.02009 Morpheus: Text-Driven 3D Gaussian Splat Shape and Color Stylization
        90940, -- 2503.04314 S2Gaussian: Sparse-View Super-Resolution 3D Gaussian Splatting
        90953, -- 2503.08382 Twinner: Shining Light on Digital Twins in a Few Snaps
        90966, -- 2412.07534 ReCap: Better Gaussian Relighting with Cross-Environment Captures
        90976, -- 2501.06897 ActiveGAMER: Active GAussian Mapping through Efficient Rendering
        90985, -- 2503.12242 RePerformer: Immersive Human-centric Volumetric Videos from Playback t
        90999, -- 2411.19235 InstanceGaussian: Appearance-Semantic Joint Gaussian Representation fo
        91008, -- 2503.00359 Solving Instance Detection from an Open-World Perspective
        91077, -- 2410.24207 No Pose, No Problem: Surprisingly Simple 3D Gaussian Splats from Spars
        91341, -- 2405.13998 CViT: Continuous Vision Transformer for Operator Learning
        91430, -- 2406.16360 Inverse Rendering using Multi-Bounce Path Tracing and Reservoir Sampli
        91502, -- 2502.10988 OMG: Opacity Matters in Material Modeling with Gaussian Splatting
        91621, -- 2502.17377 Graph-Guided Scene Reconstruction from Images with 3D Gaussian Splatti
        91626, -- 2410.22936 Bringing NeRFs to the Latent Space: Inverse Graphics Autoencoder
        91742, -- 2501.05757 Locality-aware Gaussian Compression for Fast and High-quality Renderin
        91942, -- 2406.03293 Text-to-Image Rectified Flow as Plug-and-Play Priors
        91948, -- 2410.07577 3D Vision-Language Gaussian Splatting
        91965, -- 2410.18931 Sort-free Gaussian Splatting via Weighted Sum Rendering
        91974, -- 2406.15020 A3D: Does Diffusion Dream about 3D Alignment?
        92045, -- 2410.04779 Fast Training of Sinusoidal Neural Fields via Scaling Initialization
        92059, -- 2406.12082 Uncertainty modeling for fine-tuned implicit functions
        92161, -- 2410.11682 SurFhead: Affine Rig Blending for Geometrically Accurate 2D Gaussian S
        92192, -- 2502.12640 RecDreamer: Consistent Text-to-3D Generation via Uniform Score Distill
        92426, -- 2408.13055 Atlas Gaussians Diffusion for 3D Generation
        92542, -- 2606.05102 ZipSplat: Fewer Gaussians, Better Splats
        93242, -- 2410.23742 Fused-Planes: Why Train a Thousand Tri-Planes When You Can Share?
        93253, -- 2510.09997 CLoD-GS: Continuous Level-of-Detail via 3D Gaussian Splatting
        93414, -- 2603.28090 To View Transform or Not to View Transform: NeRF-based Pre-training Pe
        93534, -- 2508.09239 Gradient-Direction-Aware Density Control for 3D Gaussian Splatting
        94032, -- 2603.00418 Station2Radar: Query‑Conditioned Gaussian Splatting for Precipitation
        94210, -- 2507.15748 CHROMA: Consistent Harmonization of Multi-View Appearance via Bilatera
        94271, -- 2603.11543 Mango-GS: Enhancing Spatio-Temporal Consistency in Dynamic Scenes Reco
        94316, -- 2602.15155 Refine Now, Query Fast: A Decoupled Refinement Paradigm for Implicit N
        94451, -- 2510.08566 D$^2$GS: Depth-and-Density Guided Gaussian Splatting for Stable and Ac
        94469, -- 2602.20461 Nonparametric Teaching of Attention Learners
        94471, -- 2510.03312 Universal Beta Splatting
        94558, -- 2602.11845 WorldTree: Towards 4D Dynamic Worlds from Monocular Video using Tree-C
        94583, -- 2603.22362 Unveiling the Mechanism of Continuous Representation Full-Waveform Inv
        94710, -- 2603.00413 DiffTrans: Differentiable Geometry-Materials Decomposition for Reconst
        94714, -- 2510.04236 Scaling Sequence-to-Sequence Generative Neural Rendering
        94776, -- 2601.21400 Mesh Splatting for End-to-end Multiview Surface Reconstruction
        94789, -- 2510.12901 SimULi: Real-Time LiDAR and Camera Simulation with Unscented Transform
        94793, -- 2602.02356 NAB: Neural Adaptive Binning for Sparse-View CT reconstruction
        94825, -- 2511.04595 UniSplat: Unified Spatio-Temporal Fusion via 3D Latent Scaffolds for D
        94839, -- 2510.10152 Color3D: Controllable and Consistent 3D Colorization with Personalized
        94925, -- 2602.02089 UrbanGS: Efficient and Scalable Architecture for Geometrically Accurat
        95152, -- 2409.14103 ExFMan: Rendering 3D Dynamic Humans with Hybrid Monocular Blurry Frame
        95337, -- 2505.14938 Scan, Materialize, Simulate: A Generalizable Framework for Physically
        95497, -- 2412.15447 LiHi-GS: LiDAR-Supervised Gaussian Splatting for Highway Driving Scene
        95549, -- 2504.04597 Targetless LiDAR-Camera Calibration with Neural Gaussian Splatting
        95765, -- 2507.18713 SaLF: Sparse Local Fields for Multi-Sensor Rendering in Real-Time
        95792, -- 2602.17101 Benchmarking the Effects of Object Pose Estimation and Reconstruction
        96055, -- 2509.12702 UDON: Uncertainty-Weighted Distributed Optimization for Multi-Robot Ne
        96110, -- 2509.08354 Grasp Like Humans: Learning Generalizable Multi-Fingered Grasping from
        96122, -- 2411.15468 SplatSDF: Boosting SDF-NeRF Via Architecture-Level Fusion with Gaussia
        96142, -- 2510.03885 Seeing the Bigger Picture: 3D Latent Mapping for Mobile Manipulation P
        96209, -- 2505.24819 Bi-Manual Joint Camera Calibration and Scene Representation
        96323, -- 2505.12693 TACOcc: Target-Adaptive Cross-Modal Fusion with Sequential Volume Rend
        96335, -- 2405.20323 Self-Supervised Street Gaussians for Autonomous Driving
        96518, -- 2502.02657 SiLVR: Scalable Lidar-Visual Radiance Field Reconstruction with Uncert
        96720, -- 2507.03886 ArmGS: Composite Gaussian Appearance Refinement for Modeling Dynamic U
        96908, -- 2507.01125 VISTA: Open-Vocabulary, Task-Relevant Robot Exploration with Online Se
        96914, -- 2504.00159 SonarSplat: Novel View Synthesis of Imaging Sonar Via Gaussian Splatti
        97466, -- 2404.06727 Bayesian NeRF: Quantifying Uncertainty with Volume Density for Neural
        97531, -- 2504.00763 UnIRe: Unsupervised Instance Decomposition for Dynamic Urban Scene Rec
        97655, -- 2603.22796 PhotoAgent: A Robotic Photographer with Spatial and Aesthetic Understa
        98239, -- 2606.13644 Surflo: Consistent 3D Surface Flow Model with Global State
        98558, -- 2604.13416 DF3DV-1K: A Large-Scale Dataset and Benchmark for Distractor-Free Nove
        98598, -- 2604.25466 Generalizable Human Gaussian Splatting via Multi-view Semantic Consist
        98606, -- 2606.15659 SpatialAvatar-0: High-Quality 4D Head Avatar with Multi-Stage Reconstr
        98958, -- 2606.30045 Walking in the Implicit: Interactive World Exploration via Neural Scen
        99212, -- 2512.14366 Optimizing Rank for High-Fidelity Implicit Neural Representations
        99674, -- 2605.12494 Revisiting Photometric Ambiguity for Accurate Gaussian-Splatting Surfa
        99962, -- 2603.07615 Compression as Adaptation: Implicit Visual Representation with Diffusi
        100148, -- 2604.09543 ANTiC: Adaptive Neural Temporal In Situ Compressor
        100343, -- 2606.02073 Planar Symmetric Pattern Generation
        100393, -- 2606.08980 EPS3D: End-to-End Feed-Forward 3D Panoptic Segmentation
        101708, -- 2606.15924 TurboGS: Accelerating 3D Gaussian Splatting via Error-Guided Sparse Pi
        103897, -- 2208.02705 360Roam: Real-Time Indoor Roaming Using Geometry-Aware 360$^\circ$ Rad
        103898, -- 2606.31556 AugSplat: Radiance Field-Informed Gaussian Splatting for Sparse-View S
        103903, -- 2412.06273 Omni-Scene: Omni-Gaussian Representation for Ego-Centric Sparse-View S
        103912, -- 2405.12110 CoR-GS: Sparse-View 3D Gaussian Splatting via Co-Regularization
        103913, -- 2403.06912 DNGaussian: Optimizing Sparse-View 3D Gaussian Radiance Fields with Gl
        103914, -- 2405.19657 Uncertainty-guided Optimal Transport in Depth Supervised Sparse-View 3
        104013, -- 2607.12000 MetaView: Monocular Novel View Synthesis with Scale-Aware Implicit Geo
        104065, -- 2607.10995 AsySplat: Efficient Asymmetric 3D Gaussian Splatting for Long-Sequence
        104482, -- 2607.20417 ATSplat: Compact Feed-forward 3D Gaussian Splatting with Adaptive Toke
        104516, -- 2607.21485 Recurrent Sinusoidal INRs for Efficient High-Fidelity Representation
        104725, -- 2306.09818 HiNeRV: Video Compression with Hierarchical Encoding-based Neural Repr
        104745, -- 2604.25936 SAND: Spatially Adaptive Network Depth for Fast Sampling of Neural Imp
        104753, -- 2605.03623 A Few-Step Generative Model on Cumulative Flow Maps
        104781, -- 2601.19683 SharpNet: Enhancing MLPs to Represent Functions with Controlled Non-di
        104782, -- 2602.05081 Gabor Fields: Orientation-Selective Level-of-Detail for Volume Renderi
        104814, -- 2510.18189 A Generalizable Light Transport 3D Embedding for Global Illumination
        104823, -- 2604.23537 Distance Field Rasterization for End-to-End Mesh Reconstruction
        104835, -- 2606.21270 Non-line-of-sight imaging with arbitrary relay surface geometries via
        104839, -- 2605.05664 Sparse-to-Complete: From Sparse Image Captures to Complete 3D Scenes
        104842, -- 2506.22899 Neural Cellular Automata: From Cells to Pixels
        104853, -- 2602.06937 Reciprocal Latent Fields for Precomputed Sound Propagation
        104876, -- 2603.07664 Ref-DGS: Reflective Dual Gaussian Splatting
        104879, -- 2605.09299 LagrangianSplats: Divergence-Free Transport of Gaussian Primitives for
        105135, -- 2501.09049 Dynamic-Aware Spatio-temporal Representation Learning for Dynamic MRI
        105539, -- 2503.00230 Physics-Informed Implicit Neural Representations for Joint B0 Estimati
        105952, -- 2607.12362 Implicit 4D Gaussian Splatting for Fast Motion with Large Inter-Frame
        106408, -- 2503.02230 Empowering Sparse-Input Neural Radiance Fields with Dual-Level Semanti
        106467, -- 2511.07122 Sparse4DGS: 4D Gaussian Splatting for Sparse-Frame Dynamic Scene Recon
        106478, -- 2504.19860 CoherenDream: Boosting Holistic Text Coherence in 3D Generation via Mu
        106527, -- 2508.19243 Style4D-Bench: A Benchmark Suite for 4D Stylization
        106558, -- 2511.11436 Unsupervised Motion-Compensated Decomposition for Cardiac MRI Reconstr
        106630, -- 2511.06046 StreamSTGS: Streaming Spatial and Temporal Gaussian Grids for Real-Tim
        106639, -- 2511.11710 Target-Balanced Score Distillation
        106757, -- 2511.08079 Deep Inverse Shading: Consistent Albedo and Surface Detail Recovery vi
        106788, -- 2511.13571 Opt3DGS: Optimizing 3D Gaussian Splatting with Adaptive Exploration an
        107173, -- 2412.03121 Splats in Splats: Robust and Effective 3D Steganography Towards Gaussi
        107186, -- 2507.05859 D-FCGS: Feedforward Compression of Dynamic Gaussian Splatting for Free
        107226, -- 2506.05011 UAV4D: Dynamic Neural Rendering of Human-Centric UAV Imagery Using Gau
        107678, -- 2511.12040 SRSplat: Feed-Forward Super-Resolution Gaussian Splatting from Sparse
        107844, -- 2412.05853 Unsupervised Multi-Parameter Inverse Solving for Reducing Ring Artifac
        107926, -- 2511.15102 Gaussian Blending: Rethinking Alpha Blending in 3D Gaussian Splatting
        108197, -- 2511.16454 LLaVA³: Representing 3D Scenes Like a Cubist Painter to Boost 3D Scene
        108289, -- 2511.12935 PFAvatar: Pose-Fusion 3D Personalized Avatar Reconstruction from Real-
        108293, -- 2511.11175 Dynamic Gaussian Scene Reconstruction from Unsynchronized Videos
        108420, -- 2511.22262 Can Protective Watermarking Safeguard the Copyright of 3D Gaussian Spl
        108436, -- 2601.00504 MotionPhysics: Learnable Motion Distillation for Text-Guided Simulatio
        108454, -- 2412.04826 Pushing Rendering Boundaries: Hard Gaussian Splatting
        108512, -- 2501.03659 DehazeGS: Seeing Through Fog with 3D Gaussian Splatting
        108520, -- 2511.20050 Active3D: Active High-Fidelity 3D Reconstruction via Multi-Level Uncer
        108657, -- 2608.02713 Quo Vadis, World Modeling?
        108729, -- 2608.04701 UniWorld-View: Large-Baseline View Synthesis via Video Diffusion Model
        108753, -- 2411.18966 SVGS: Enhancing Gaussian Splatting Using Primitives with Spatially Var
        108778, -- 2605.07287 SplatWeaver: Learning to Allocate Gaussian Primitives for Generalizabl
        109482, -- 2407.20219 Global Structure-from-Motion Revisited
        109856, -- 2305.14831 OD-NeRF: Efficient Training of On-the-Fly Dynamic Neural Radiance Fiel
        109858, -- 2411.19271 AGS-Mesh: Adaptive Gaussian Splatting and Meshing with Geometric Prior
        109862, -- 2502.13968 Betsu-Betsu: Multi-View Separable 3D Reconstruction of Two Interacting
        109863, -- 2403.16862 INPC: Implicit Neural Point Clouds for Radiance Field Rendering
        109866, -- 2404.09531 Oblique-MERF: Revisiting and Improving MERF for Oblique Photography
        109868, -- 2408.06286 Mipmap-GS: Let Gaussians Deform with Scale-Specific Mipmap for Anti-Al
        109871, -- 2402.03723 Rig3DGS: Creating Controllable Portraits From Casual Monocular Videos
        109876, -- 2409.06104 LSE-NeRF: Learning Sensor Modeling Errors for Deblured Neural Radiance
        109883, -- 2409.03061 Incorporating Dense Metric Depth into Neural 3D Representations for Vi
        109886, -- 2501.15722 INRet: A General Framework for Accurate Retrieval of INRs for Shapes
        109899, -- 2406.19811 EgoGaussian: Dynamic Scene Understanding from Egocentric Video with 3D
        109902, -- 2502.01405 FourieRF: Few-Shot NeRFs via Progressive Fourier Frequency Control
        109905, -- 2406.18360 XLD: A Cross-Lane Dataset for Benchmarking Novel Driving View Synthesi
        109918, -- 2502.10827 E-3DGS: Event-Based Novel View Rendering of Large-Scale Scenes Using 3
        109919, -- 2409.15689 Plenoptic PNG: Real-Time Neural Radiance Fields in 150 KB
        109929, -- 2501.09259 OpticFusion: Multi-Modal Neural Implicit 3D Reconstruction of Microstr
        109932, -- 2310.16858 4D-Editor: Interactive Object-Level Editing in Dynamic Neural Radiance
        109933, -- 2409.02104 DynOMo: Online Point Tracking by Dynamic Online Monocular Gaussian Rec
        112176, -- 2509.23336 DiffTex: Differentiable Texturing for Architectural Proxy Models
        112184, -- 2509.18497 Differentiable Light Transport with Gaussian Surfels via Adapted Radio
        112187, -- 2506.24096 MILo: Mesh-In-the-Loop Gaussian Splatting for Detailed and Efficient S
        112219, -- 2511.21697 Detail Enhanced Gaussian Splatting for Large-Scale Volumetric Capture
        112221, -- 2509.22227 Aerial Path Planning for Urban Geometry and Texture Co-Capture
        112243, -- 2508.07852 Vertex Features for Neural Global Illumination
        112251, -- 2512.10424 Neural Hamiltonian Deformation Fields for Dynamic Scene Rendering
        112256, -- 2505.21041 CityGo: Lightweight Urban Modeling and Rendering with Proxy Buildings
        112275, -- 2409.12771 Spectral-GS: Taming 3D Gaussian Splatting with Spectral Entropy
        112312, -- 2512.07807 Lang3D-XL: Language Embedded 3D Gaussians for Large-scale Scenes
        112313, -- 2509.25001 LVT: Large-Scale Scene Reconstruction via Local View Transformers
        112319, -- 2506.19139 SOF: Sorted Opacity Fields for Fast Unbounded Surface Reconstruction
        112332, -- 2511.16112 Clustered Error Correction with Grouped 4D Gaussian Splatting
        112356, -- 2511.18873 Neural Texture Splatting: Expressive 3D Gaussian Splatting for View Sy
        112366, -- 2504.15933 Low-Rank Adaptation of Neural Fields
        112444, -- 2407.09352 Imaging Interiors: An Implicit Solution to Electromagnetic Inverse Sca
        112472, -- 2407.13390 GeometrySticker: Enabling Ownership Claim of Recolorized Neural Radian
        112480, -- 2408.09347 S^3D-NeRF: Single-Shot Speech-Driven Neural Radiance Field for High Fi
        112488, -- 2407.07735 Protecting NeRFs' Copyright via Plug-And-Play Watermarking Base Model
        112494, -- 2407.04699 LaRa: Efficient Large-Baseline Radiance Fields
        112499, -- 2403.11909 RoGUENeRF: A Robust Geometry-Consistent Universal Enhancer for NeRF
        112506, -- 2408.10739 TrackNeRF: Bundle Adjusting NeRF from Sparse and Noisy Views via Featu
        112526, -- 2408.03753 3iGS: Factorised Tensorial Illumination for 3D Gaussian Splatting
        112534, -- 2408.15524 Ray-Distance Volume Rendering for Neural Scene Reconstruction
        112543, -- 2408.02672 Latent-INR: A Flexible Framework for Implicit Representations of Video
        112549, -- 2407.05254 GaussReg: Fast 3D Registration with Gaussian Splatting
        112557, -- 2305.15171 Diffusion-Generated Pseudo-Observations for High-Quality Sparse-View R
        112570, -- 2402.00752 On the Error Analysis of 3D Gaussian Splatting and an Optimal Projecti
        112601, -- 2403.15530 Pixel-GS Density Control with Pixel-aware Gradient for 3D Gaussian Spl
        112663, -- 2403.09577 The Nerfect Match: Exploring NeRF Features for Visual Localization
        112675, -- 2403.10050 Texture-GS: Disentangle the Geometry and Texture for 3D Gaussian Splat
        112677, -- 2403.16095 CG-SLAM: Efficient Dense RGB-D SLAM in a Consistent Uncertainty-aware
        112704, -- 2407.12291 JointDreamer: Ensuring Geometry Consistency and Text Congruence in Tex
        112709, -- 2407.11347 I2-SLAM: Inverting Imaging Process for Robust Photorealistic Dense SLA
        112717, -- 2409.08042 Thermal3D-GS: Physics-induced 3D Gaussians for Thermal Infrared Novel-
        112721, -- 2405.17429 GaussianFormer: Scene as Gaussians for Vision-Based 3D Semantic Occupa
        112724, -- 2409.05867 Flash Cache: Reducing Bias in Radiance Cache Based Inverse Rendering
        112743, -- 2407.13592 MeshFeat: Multi-Resolution Features for Neural Fields on Meshes
        112774, -- 2402.03246 SGS-SLAM: Semantic Gaussian Splatting For Neural Dense SLAM
        112782, -- 2407.02174 BeNeRF:Neural Radiance Fields from a Single Blurry Image and Event Str
        112792, -- 2409.03634 Surface-Centric Modeling for High-Fidelity Generalizable Neural Surfac
        112820, -- 2409.09756 MesonGS: Post-training Compression of 3D Gaussians via Efficient Attri
        112840, -- 2312.03357 RING-NeRF : Rethinking Inductive Biases for Versatile and Efficient Ne
        112852, -- 2403.11324 GeoGaussian: Geometry-aware Gaussian Splatting for Scene Rendering
        112853, -- 2403.10119 URS-NeRF: Unordered Rolling Shutter Bundle Adjustment for Neural Radia
        112857, -- 2403.12550 RGBD GS-ICP SLAM
        112863, -- 2409.18953 UniCal: Unified Neural Sensor Calibration
        112874, -- 2506.08619 A Probability-guided Sampler for Neural Implicit Surface Rendering
        112878, -- 2403.14053 Leveraging Thermal Modality to Enhance Reconstruction in Low-Light Con
        112882, -- 2407.00021 Neural graphics texture compression supporting random access
        112890, -- 2312.02362 "PointNeRF++: A multi-scale, point-based Neural Radiance Field"
        112897, -- 2312.05283 Nuvo: Neural UV Mapping for Unruly 3D Representations
        112987, -- 2407.13185 KFD-NeRF: Rethinking Dynamic NeRF with Kalman Filter
        113017, -- 2409.14316 MVPGS: Excavating Multi-view Priors for Gaussian Splatting from Sparse
        113050, -- 2409.15715 Disentangled Generation and Aggregation for Robust Radiance Fields
        113051, -- 2212.10950 UNIKD: UNcertainty-Filtered Incremental Knowledge Distillation for Neu
        113060, -- 2403.19160 Within the Dynamic Context: Inertia-aware 3D Human Modeling with Pose
        113071, -- 2404.04908 Dual-Camera Smooth Zoom on Mobile Phones
        113123, -- 2408.02110 AvatarPose: Avatar-guided 3D Pose Estimation of Close Human Interactio
        113138, -- 2311.16937 The Sky's the Limit: Relightable Outdoor Scenes via a Sky-pixel Constr
        113155, -- 2312.13308 SWinGS: Sliding Windows for Dynamic 3D Gaussian Splatting
        113166, -- 2410.00672 GMT: Enhancing Generalizable Neural Rendering via Geometry-Driven Mult
        113217, -- 2408.02079 Improving Neural Surface Reconstruction with Feature Priors from Multi
        113226, -- 2403.13199 DecentNeRFs: Decentralized Neural Radiance Fields from Crowdsourced Im
        113232, -- 2404.10681 StyleCity: Large-Scale 3D Urban Scenes Stylization
        113235, -- 2401.03704 Sur^2f: A Hybrid Representation for High-Quality and Efficient Surface
        113236, -- 2403.20032 HO-Gaussian: Hybrid Optimization of 3D Gaussian Splatting for Urban Sc
        113243, -- 2404.03349 VF-NeRF: Viewshed Fields for Rigid NeRF Registration
        113259, -- 2408.05533 UAV First-Person Viewers Are Radiance Field Learners
        113283, -- 2311.12063 DatasetNeRF: Efficient 3D-aware Data Factory with Generative Radiance
        113293, -- 2312.02202 Volumetric Rendering with Baked Quadrature Fields
        113365, -- 2404.03654 RaFE: Generative Radiance Fields Restoration
        113388, -- 2405.19321 DGD: Dynamic 3D Gaussians Distillation
        113414, -- 2401.08398 High-Quality Mesh Blendshape Generation from Face Videos via Neural In
        113456, -- 2407.15554 Decomposition of Neural Discrete Representations for Large-Scale 3D Ma
        113457, -- 2405.11921 MirrorGaussian: Reflecting 3D Gaussians for Reconstructing Mirror Refl
        113484, -- 2409.06923 Rethinking Directional Parameterization in Neural Implicit Surface Rec
        113486, -- 2505.00335 Efficient Neural Video Representation with Temporally Coherent Modulat
        113503, -- 2312.02192 Diverse Text-to-3D Synthesis with Augmented Text Embedding
        113515, -- 2312.09780 RANRAC: Robust Neural Scene Representations via Random Ray Consensus
        113529, -- 2403.14166 Mini-Splatting: Representing Scenes with a Constrained Number of Gauss
        113532, -- 2403.09079 PreSight: Enhancing Autonomous Vehicle Perception with City-Scale NeRF
        113561, -- 2312.00112 DynMF: Neural Motion Factorization for Real-time Dynamic View Synthesi
        113580, -- 2403.04926 BAGS: Blur Agnostic Gaussian Splatting through Multi-Scale Kernel Mode
        113588, -- 2404.00875 DPA-Net: Structured 3D Abstraction from Sparse Views via Differentiabl
        113623, -- 2407.10389 Boost Your NeRF: A Model-Agnostic Mixture of Experts Framework for Hig
        113629, -- 2405.02508 Rasterized Edge Gradients: Handling Discontinuities Differentially
        113701, -- 2407.09822 VividDreamer: Invariant Score Distillation for Hyper-Realistic Text-to
        113827, -- 2608.29137 Chat-Edit-3D++: Interactive 3D and 4D Scene Editing via Large Language
        113978, -- 2412.15278 DreaMark: Rooting Watermark in Score Distillation Sampling Generated N
        114437, -- 2403.08550 CINA: Conditional Implicit Neural Atlas for Spatio-Temporal Representa
        115010, -- 2407.02974 IM-MoCo: Self-supervised MRI Motion Correction using Motion-Guided Imp
        115030, -- 2409.11983 Intraoperative Registration by Cross-Modal Inverse Neural Rendering
        115234, -- 2407.14846 Realistic Surgical Image Dataset Generation Based On 3D Gaussian Splat
        115463, -- 2403.16224 Inverse Rendering of Glossy Objects via the Neural Plenoptic Function
        115493, -- 2312.03420 Artist-Friendly Relightable and Animatable Neural Heads
        115533, -- 2404.00676 OmniLocalRF: Omnidirectional Local Radiance Fields from Dynamic Videos
        115546, -- 2404.02185 NeRFCodec: Neural Feature Compression Meets Neural Radiance Fields for
        115562, -- 2404.00149 VSRD: Instance-Aware Volumetric Silhouette Rendering for Weakly Superv
        115571, -- 2403.03896 DART: Implicit Doppler Tomography for Radar Novel View Synthesis
        115576, -- 2307.00842 VINECS: Video-based Neural Character Skinning
        115579, -- 2405.02066 WateRF: Robust Watermarks in Radiance Fields for Protection of Copyrig
        115583, -- 2311.04246 ADFactory: An Effective Framework for Generalizing Optical Flow with N
        115587, -- 2405.03388 3D LiDAR Mapping in Dynamic Environments using a 4D Implicit Neural Re
        115608, -- 2302.04871 In-N-Out: Faithful 3D GAN Inversion with Volumetric Decomposition for
        115624, -- 2312.02137 MANUS: Markerless Grasp Capture using Articulated 3D Gaussians
        115662, -- 2306.00519 DiffInDScene: Diffusion-based High-Quality 3D Indoor Scene Generation
        115698, -- 2311.17754 Cinematic Behavior Transfer via NeRF-based Differentiable Filming
        115762, -- 2307.16897 DiVa-360: The Dynamic Visual Dataset for Immersive Neural Fields
        115775, -- 2312.02209 AttriHuman-3D: Editable 3D Human Avatar Generation with Attribute Deco
        115785, -- 2404.00678 OmniSDF: Scene Reconstruction using Omnidirectional Signed Distance Fu
        115796, -- 2403.11812 Aerial Lifting: Neural Urban Semantic and Building Instance Lifting fr
        115830, -- 2403.17638 Learning with Unreliability: Fast Few-shot Voxel Radiance Fields with
        115838, -- 2403.06205 S-DyRF: Reference-Based Stylized Radiance Fields for Dynamic Scenes
        115870, -- 2403.20018 SCINeRF: Neural Radiance Fields from a Snapshot Compressive Image
        115871, -- 2311.13099 PIE-NeRF: Physics-based Interactive Elastodynamics with NeRF
        115913, -- 2311.15637 Neural 3D Strokes: Creating Stylized 3D Scenes with Vectorized 3D Stro
        115921, -- 2403.17801 Towards 3D Vision with Low-Cost Single-Photon Cameras
        115931, -- 2406.04155 Improving Physics-Augmented Continuum Neural Radiance Field-Based Geom
        115959, -- 2403.01414 Unsigned Orthogonal Distance Fields: An Accurate Neural Implicit Repre
        116084, -- 2311.10959 Structure-Aware Sparse-View X-ray 3D Reconstruction
        116094, -- 2403.03608 GSNeRF: Generalizable Semantic Neural Radiance Fields with Enhanced 3D
        116095, -- 2404.02155 Alpha Invariance: On Inverse Scaling Between Distance and Volume Densi
        116114, -- 2403.17537 NeRF-HuGS: Improved Neural Radiance Fields in Non-static Scenes Using
        116129, -- 2404.06851 UDiFF: Generating Conditional Unsigned Distance Fields with Optimal Wa
        116134, -- 2312.06713 TeTriRF: Temporal Tri-Plane Radiance Fields for Efficient Free-Viewpoi
        116146, -- 2402.17364 Learning Dynamic Tetrahedra for High-Quality Talking Head Synthesis
        116161, -- 2404.00874 DiSR-NeRF: Diffusion-Guided View-Consistent Super-Resolution NeRF
        116177, -- 2312.09558 Towards Transferable Targeted 3D Adversarial Attack in the Physical Wo
        116210, -- 2404.13024 BANF: Band-Limited Neural Fields for Levels of Detail Reconstruction
        116257, -- 2405.19876 IReNe: Instant Recoloring of Neural Radiance Fields
        116270, -- 2405.00900 LidaRF: Delving into Lidar for Neural Radiance Field on Street Scenes
        116272, -- 2312.02434 FINER: Flexible Spectral-bias Tuning in Implicit NEural Representation
        116305, -- 2404.02742 LiDAR4D: Dynamic Neural Fields for Novel Space-time View LiDAR Synthes
        116350, -- 2401.12592 RGBD Objects in the Wild: Scaling Real-World 3D Object Learning from R
        116360, -- 2404.00931 GOV-NeSF: Generalizable Open-Vocabulary Neural Semantic Fields
        116372, -- 2312.07920 DrivingGaussian: Composite Gaussian Splatting for Surrounding Dynamic
        116390, -- 2406.10543 NeRFDeformer: NeRF Transformation from a Single View via 3D Scene Flow
        116409, -- 2403.18356 MonoHair: High-Fidelity Hair Modeling from a Monocular Video
        116414, -- 2404.13541 Generalizable Novel-View Synthesis using a Stereo Camera
        116415, -- 2312.05247 Dynamic LiDAR Re-simulation using Compositional Neural Fields
        116474, -- 2402.17483 AlignMiF: Geometry-Aligned Multimodal Implicit Field for LiDAR-Camera
        116495, -- 2406.08839 NeRF Director: Revisiting View Selection in Neural Volume Rendering
        116518, -- 2311.11016 SNI-SLAM: Semantic Neural Implicit SLAM
        116523, -- 2403.15679 DS-NeRV: Implicit Neural Video Representation with Decomposed Static a
        116544, -- 2312.14235 Neural Spline Fields for Burst Image Fusion and Layer Separation
        116548, -- 2312.13328 NeLF-Pro: Neural Light Field Probes for Multi-Scale Novel View Synthes
        116601, -- 2403.10103 DyBluRF: Dynamic Neural Radiance Fields from Blurry Monocular Video
        116602, -- 2401.02436 Compressed 3D Gaussian Splatting for Accelerated Novel View Synthesis
        116606, -- 2404.08921 PNeRV: Enhancing Spatial Consistency via Pyramidal Neural Representati
        116667, -- 2311.18695 Seg2Reg: Differentiable 2D Segmentation to 1D Regression Rendering for
        116695, -- 2312.03442 High-Quality Facial Geometry and Appearance Capture at Home
        116729, -- 2312.02232 HumanNeRF-SE: A Simple yet Effective Approach to Animate HumanNeRF wit
        116738, -- 2312.00778 MorpheuS: Neural Dynamic 360deg Surface Reconstruction from Monocular
        116752, -- 2405.00340 NC-SDF: Enhancing Indoor Scene Reconstruction Using Neural SDFs with V
        116765, -- 2404.12887 3D Multi-frame Fusion for Video Stabilization
        116770, -- 2405.19819 Gated Fields: Learning Scene Reconstruction from Gated Videos
        116780, -- 2406.06948 Neural Visibility Field for Uncertainty-Driven Active Mapping
        116786, -- 2312.05664 CoGS: Controllable Gaussian Splatting
        116793, -- 2405.19295 3D Neural Edge Reconstruction
        116832, -- 2406.09402 Instruct 4D-to-4D: Editing 4D Scenes as Pseudo-3D Scenes Using 2D Diff
        116834, -- 2311.16728 Photo-SLAM: Real-time Simultaneous Localization and Photorealistic Map
        116881, -- 2403.06908 FreGS: 3D Gaussian Splatting with Progressive Frequency Regularization
        116910, -- 2404.00524 TexVocab: Texture Vocabulary-conditioned Human Avatars
        116920, -- 2311.12754 SelfOcc: Self-Supervised Vision-Based 3D Occupancy Prediction
        116928, -- 2403.20002 Grounding and Enhancing Grid-based Models for Neural Fields
        116930, -- 2404.15707 ESR-NeRF: Emissive Source Reconstruction Using LDR Multi-view Images
        116938, -- 2311.16099 GART: Gaussian Articulated Template Models
        116961, -- 2310.08332 Real-Time Neural BRDF with Spherically Distributed Primitives
        116996, -- 2311.07044 L0-Sampler: An L0 Model Guided Volume Sampling for NeRF
        117027, -- 2404.14410 Guess The Unseen: Dynamic 3D Scene Reconstruction from Partial 2D Glim
        117032, -- 2404.03652 The More You See in 2D the More You Perceive in 3D
        117043, -- 2311.15803 SOAC: Spatio-Temporal Overlap-Aware Multi-Sensor Calibration using Neu
        117051, -- 2402.09944 Loopy-SLAM: Dense Neural SLAM with Loop Closures
        117067, -- 2312.09913 LAENeRF: Local Appearance Editing for Neural Radiance Fields
        117087, -- 2311.17089 Multi-Scale 3D Gaussian Splatting for Anti-Aliased Rendering
        117089, -- 2403.04583 Unbiased Estimator for Distorted Conics in Camera Calibration
        117091, -- 2404.00168 Multi-Level Neural Scene Graphs for Dynamic Urban Environments
        117095, -- 2403.16885 CVT-xRF: Contrastive In-Voxel Transformer for 3D Consistent Radiance F
        117107, -- 2404.07474 G-NeRF: Geometry-enhanced Novel View Synthesis from Single-View Images
        117117, -- 2403.19517 XScale-NVS: Cross-Scale Novel View Synthesis with Hash Featurized Mani
        117119, -- 2404.10438 The Unreasonable Effectiveness of Pre-Trained Features for Camera Pose
        117157, -- 2305.16321 Eclipse: Disambiguating Illumination and Materials using Unintended Sh
        117186, -- 2403.07222 You'll Never Walk Alone: A Sketch and Text Duet for Fine-Grained Image
        117191, -- 2312.06740 MonoNPHM: Dynamic Head Reconstruction from Monocular Videos
        117207, -- 2403.19314 Total-Decom: Decomposed 3D Scene Reconstruction with Minimal Interacti
        117208, -- 2312.00075 Accelerating Neural Field Training via Soft Mining
        117212, -- 2406.03723 Gear-NeRF: Free-Viewpoint Rendering and Tracking with Motion-aware Spa
        117236, -- 2305.15094 InNeRF360: Text-Guided 3D-Consistent Object Inpainting on 360-degree N
        117243, -- 2404.04562 Diffusion Time-step Curriculum for One Image to 3D Generation
        117244, -- 2309.11281 Language-driven Object Fusion into Neural Radiance Fields with Pose-Co
        117252, -- 2504.18468 RGS-DR: Deferred Reflections and Residual Shading in 2D Gaussian Splat
        117262, -- 2508.14278 GALA: Guided Attention with Language Alignment for Open Vocabulary Gau
        117266, -- 2411.15355 UniGaussian: Driving Scene Reconstruction from Multiple Camera Models
        117268, -- 2502.14789 Structurally Disentangled Feature Fields Distillation for 3D Understan
        117273, -- 2601.12285 LegacyAvatars: Volumetric Face Avatars For Traditional Graphics Pipeli
        117274, -- 2505.10827 NeuSEditor: From Multi-View Images to Text-Guided Neural Surface Edits
        117277, -- 2501.03932 J-NeuS: Joint field optimization for Neural Surface reconstruction in
        117280, -- 2511.03950 Improving Multi-View Reconstruction via Texture-Guided Gaussian-Mesh J
        117284, -- 2505.16565 M2SVid: End-to-End Inpainting and Refinement for Monocular-to-Stereo V
        117297, -- 2412.18600 ZeroHSI: Zero-Shot 4D Human-Scene Interaction by Video Generation
        117305, -- 2504.12905 Matrix-free Second-order Optimization of Gaussian Splats with Residual
        117308, -- 2512.14406 Broadening View Synthesis of Dynamic Scenes from Constrained Monocular
        117314, -- 2503.21226 Frequency-Aware Gaussian Splatting Decomposition
        117340, -- 2505.04612 FastMap: Revisiting Structure from Motion through First-Order Optimiza
        117353, -- 2412.13897 Data-Efficient Inference of Neural Fluid Fields via SciML Foundation M
        117357, -- 2506.13348 TextureSplat: Per-Primitive Texture Mapping for Reflective Gaussian Sp
        117368, -- 2605.26328 RadarSim: Simulating Single-Chip Radar via Multimodal Neural Fields
        117392, -- 2606.30677 DANTE-W: Diffuse Albedo Neural Texturing in the Wild
        117413, -- 2606.32036 PointSplat: Compact Gaussian Splatting via Human-Centric Prediction
        117424, -- 2605.11913 Vector Scaffolding: Inter-Scale Orchestration for Differentiable Image
        117470, -- 2504.13207 BEV-GS: Feed-forward Gaussian Splatting in Bird’s-Eye-View for Road Re
        117476, -- 2607.19765 Extending a Large View Synthesis Model for Multi-view Panoptic Segment
        117478, -- 2607.20813 SubSplat: High-Resolution Pixel-aligned 3DGS via Sub-pixel Gaussian Re
        117487, -- 2607.02712 Global Pose Control for Generative View Synthesis in Normalized Object
        117523, -- 2603.19834 Fourier Splatting: Generalized Fourier encoded primitives for scalable
        117527, -- 2608.21828 Towards Alias-Free 4D Gaussian Representations with Motion-Aware Filte
        117530, -- 2606.29329 RAGA: Real Time Ray Traced Gaussian Shadow Casting for 3DGS Avatar-Sce
        117531, -- 2601.03024 SA-ResGS: Self-Augmented Residual 3D Gaussian Splatting for Next Best
        117541, -- 2604.07337 From Blobs to Spokes: High-Fidelity Surface Reconstruction via Oriente
        117546, -- 2607.03765 Sparse-View Surface Reconstruction using Gaussian Splatting through Hi
        117548, -- 2603.15368 IRIS: Intersection-aware Ray-based Implicit Editable Scenes
        117576, -- 2606.26754 Capacity-Controlled Multi-View Stylization of 3D Gaussian Splatting
        117579, -- 2511.16273 TetraSDF: Analytic Isosurface Extraction with Multi-resolution Tetrahe
        117582, -- 2608.01761 DecoupleGS: Interactive 3D Gaussian Splatting for End-to-End Autonomou
        117588, -- 2603.24994 Relaxed Rigidity with Ray-based Grouping for Dynamic Gaussian Splattin
        117592, -- 2607.01578 MVFusion-GS: Motion-Variance Guided Temporal Attention for High-Qualit
        117594, -- 2606.23212 Temporally Aware Densification for Dynamic 3D Gaussian Splatting
        117609, -- 2603.21695 RefracGS: Novel View Synthesis Through Refractive Water Surfaces with
        117611, -- 2603.16736 World Reconstruction From Inconsistent Views
        117615, -- 2603.24725 Confidence-Based Mesh Extraction from 3D Gaussians
        117617, -- 2604.01204 Neural Harmonic Textures for High-Quality Primitive Based Neural Recon
        117626, -- 2608.22344 Fast and Compact 3D Gaussian Splatting with Polarized Opacity Prior
        117631, -- 2606.03877 MLP Splatting: Object-Centric Neural Fields
        117635, -- 2608.26948 KISS-GS: 3D Gaussian Splatting Compression Kept Simple
        117636, -- 2605.31419 Triangle Splatting SLAM
        117650, -- 2607.22446 Deformable Triangle Splatting: Flexible Primitives for Real-Time Radia
        117653, -- 2607.03771 City-Level 3D Surface Reconstruction with Viewpoint Orientation Partit
        117683, -- 2607.24436 MSVS-VAE: Multi-Scale Anchored VecSet for High-Fidelity 3D Reconstruct
        117711, -- 2604.08945 TouchAnything: Diffusion-Guided 3D Reconstruction from Sparse Robot To
        117720, -- 2603.22851 UniQueR: Unified Query-based Feedforward 3D Reconstruction
        117775, -- 2511.17133 Off the Planckian Locus: Using 2D Chromaticity to Improve In-Camera Co
        117892, -- 2607.09329 Dynamic Inverse Rendering for Enhanced Material-Lighting Decomposition
        118242, -- 2607.03855 PRISM3D: Probabilistic Refinement and Robust Initialization for Physic
        118248, -- 2604.01641 LivingWorld: Interactive 4D World Generation with Environmental Dynami
        118277, -- 2604.19702 Face Anything: 4D Face Reconstruction from Any Image Sequence
        118314, -- 2606.03921 GARDEN: Gravity-Aligned Reconstruction of Disentangled ENvironments fr
        118324, -- 2607.08398 HoloTetSphere: Unified TetSphere Mesh Reconstruction for Physical Simu
        119100, -- 2606.26763 Calibrated Harmonic Overlaid Implicit Neural Representations for Multi
        119194, -- 2608.10500 DSAR: Dual-Stream Autoregressive Modeling of Temporal Cloth Dynamics f
        119196, -- 2412.02421 TimeWalker: Personalized Neural Space for Lifelong Head Avatars
        119308, -- 2603.17975 AHOY! Animatable Humans under Occlusion from YouTube Videos with Gauss
        119707, -- 2312.13494 Visual Tomography: Physically Faithful Volumetric Models of Partially
        119713, -- 2302.03594 NICER-SLAM: Neural Implicit Scene Encoding for RGB SLAM
        119718, -- 2406.09801 RaNeuS: Ray-adaptive Neural Surface Reconstruction
        119745, -- 2403.19985 Stable Surface Regularization for Fast Few-Shot NeRF
        119752, -- 2401.06052 Fast High Dynamic Range Radiance Fields for Dynamic Scenes
        119768, -- 2306.07598 Learning to Estimate 6DoF Pose from Limited Data: A Few-Shot, Generali
        119780, -- 2406.08463 Self-Supervised Learning of Neural Implicit Feature Fields for Camera
        119782, -- 2211.14485 FastHuman: Reconstructing High-Quality Clothed Human in Minutes
        119784, -- 2402.06752 Oriented-grid Encoder for 3D Implicit Representations
        119804, -- 2312.05046 MuVieCAST: Multi-View Consistent Artistic Style Transfer
        119808, -- 2311.08159 DynamicSurf: Dynamic Neural RGB-D Surface Reconstruction With an Optim
        119809, -- 2303.08096 MELON: NeRF with Unposed Images in SO(3)
        119812, -- 2403.14412 CombiNeRF: A Combination of Regularization Techniques for Few-Shot Neu
        119817, -- 2312.05855 NeVRF: Neural Video-Based Radiance Fields for Long-Duration Sequences
        119820, -- 2305.09566 Ray-Patch: An Efficient Querying for Light Field Transformers
        119823, -- 2308.04868 InstantAvatar: Efficient 3D Head Reconstruction via Surface Rendering
        119838, -- 2506.07996 UA-Pose: Uncertainty-Aware 6D Object Pose Estimation and Online Object
        119885, -- 2412.09680 PBR-NeRF: Inverse Rendering with Physics-Based Neural Fields
        120077, -- 2411.16785 MAGiC-SLAM: Multi-Agent Gaussian Globally Consistent SLAM
        120119, -- 2503.12535 SPC-GS: Gaussian Splatting with Semantic-Prompt Consistency for Indoor
        120127, -- 2409.13222 3D-GSW: 3D Gaussian Splatting for Robust Watermarking
        120133, -- 2405.17351 DOF-GS: Adjustable Depth-of-Field 3D Gaussian Splatting for Post-Captu
        120183, -- 2503.18682 Hardware-Rasterized Ray-Based Gaussian Splatting
        120306, -- 2503.13961 BG-Triangle: Bezier Gaussian Triangle for 3D Vectorization and Renderi
        120313, -- 2412.01745 Horizon-GS: Unified 3D Gaussian Splatting for Large-Scale Aerial-to-Gr
        120316, -- 2412.00905 Ref-GS: Directional Factorization for 2D Gaussian Splatting
        120467, -- 2412.03371 SGSST: Scaling Gaussian Splatting Style Transfer
        120499, -- 2503.19976 Thin-Shell-SfT: Fine-Grained Monocular Non-rigid 3D Surface Tracking w
        120526, -- 2305.17929 Factored-NeuS: Reconstructing Surfaces, Illumination, and Materials of
        120632, -- 2503.10464 Flow-NeRF: Joint Learning of Geometry, Poses, and Dense Flow within Un
        120704, -- 2603.01601 Dehallu3D: Hallucination-Mitigated 3D Generation from a Single Image v
        120787, -- 2505.20967 RF4D:Neural Radar Fields for Novel View Synthesis in Outdoor Dynamic S
        120927, -- 2604.10994 LumiMotion: Improving Gaussian Relighting with Scene Dynamics
        121009, -- 2605.29136 Eulerian Gaussian Splatting using Hashed Probability Pyramids
        121177, -- 2512.13157 Intrinsic Image Fusion for Multi-View 3D Material Reconstruction
        121288, -- 2604.00548 Reliev3R: Relieving Feed-forward 3D Reconstruction from Multi-View Geo
        121347, -- 2603.08147 MV-Fashion: Towards Enabling Virtual Try-On and Size Estimation with M
        121588, -- 2602.22212 Neu-PiG: Neural Preconditioned Grids for Fast Dynamic Surface Reconstr
        121620, -- 2605.09662 BEA-GS: BEyond RAdiance Supervision in 3DGS for Precise Object Extract
        121654, -- 2601.03357 RelightAnyone: A Generalized Relightable 3D Gaussian Head Model
        121700, -- 2605.30342 Uncertainty-driven 3D Gaussian Splatting Active Mapping via Anisotropi
        121829, -- 2510.09364 VAD-GS: Visibility-Aware Densification for 3D Gaussian Splatting in Dy
        121910, -- 2605.29098 Seeing through boxes: Non-Line-of-Sight 3D Reconstruction from Radar S
        121916, -- 2604.03716 CGHair: Compact Gaussian Hair Reconstruction with Card Clustering
        122365, -- 2609.35734 GeoVerse: World-Consistent Novel View Synthesis in Geometric Latent Sp
        122883, -- 2610.05289 Mobile-4DGS: Unified Static-Dynamic Real-time Mobile Gaussian Splattin
        123999, -- 2610.13177 CompactSplat: Spatially Adaptive Gaussian Distribution for Feedforward
        124081, -- 2402.00525 StopThePop: Sorted Gaussian Splatting for View-Consistent Real-time Re
        124123, -- 2309.08927 DynaMoN: Motion-Aware Fast and Robust Camera Localization for Dynamic
        124277, -- 2605.08298 What Cohort INRs Encode, and Where to Freeze Them
        125276, -- 2512.04974 Efficient Generative Transformer Operators for Million-Point PDEs
        125726, -- 2610.03717 Less Decoder is More Encoder: Geometric Representation Learning from N
        125859, -- 2510.12174 UniGS: Unified Geometry-Aware Gaussian Splatting for Multimodal Render
        125982, -- 2607.19120 Latent Riemannian Flow Matching for Geometry-Grounded 3D Foundation Mo
        126279, -- 2605.11967 H2G: Hierarchy-Aware Hyperbolic Grouping for 3D Scenes
        126566, -- 2610.07419 Learnable Spectral Activations
        127117, -- 2610.21634 Anchor3DGS: Feed-Forward 3D Gaussian Splatting with Compact Anchor-Bas
        127331, -- 2605.07351 Disambiguating 2D-3D Correspondences in Gaussian Splatting-based Featu
        127639, -- 2511.21098 Pygmalion Effect in Vision: Image-to-Clay Translation for Reflective G
        128432, -- 2606.02096 WebSpline: Structure-Informed Splines for Real-Time 3D Gaussians from
        129397, -- 2609.37115 NRF-GS: Neural Residual Fields for Expressive and Compact Gaussian Spl
        129800, -- 2609.28684 M-plicits: Neural Implicit Surfaces via Nested Multiscale Residuals
        130498, -- 2609.33969 Gaussian Splatting-based Volumetric Video Compression with Sparse 4D A
        130499, -- 2607.18237 The Many Senses of Visual Similarity: A Text-Prompted Image Perceptual
        130642, -- 2601.07540 Enhancing Novel View Synthesis via Geometry Grounded Set Diffusion
        131408, -- 2508.08252 ReferSplat: Referring Segmentation in 3D Gaussian Splatting
        131921  -- 2611.07909 EDGAR: Efficient Diffusion-Driven Gaussian Avatar Refinement via Synth
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
        3201, -- 2003.04618 Convolutional Occupancy Networks
        7509, -- 2112.07945 Efficient Geometry-aware 3D Generative Adversarial Networks
        11709, -- 2211.16677 3D Neural Field Generation using Triplane Diffusion
        13614, -- 2303.05371 3DGen: Triplane Latent Diffusion for Textured Mesh Generation
        14039, -- 2303.13071 PanoHead: Geometry-Aware 3D Full-Head Synthesis in 360$^{\circ}$
        14467, -- 2304.02163 GINA-3D: Learning to Generate Implicit Neural Assets in the Wild
        16248, -- 2305.15399 Sin3DM: Learning a Diffusion Model from a Single 3D Textured Shape
        18373, -- 2307.09323 Efficient Region-Aware Neural Radiance Fields for High-Fidelity Talkin
        19011, -- 2308.03757 3D Motion Magnification: Visualizing Subtle Motions with Time Varying
        19436, -- 2308.09712 HumanLiff: Layer-wise 3D Human Generation with Diffusion Model
        20436, -- 2309.07920 Large-Vocabulary 3D Diffusion Model with Transformer
        20601, -- 2309.10336 Anti-Aliased Neural Implicit Surfaces with Encoding Level of Detail
        20917, -- 2309.14600 Progressive Text-to-3D Generation for Automatic 3D Prototyping
        21219, -- 2310.01140 Neural Processing of Tri-Plane Hybrid Neural Fields
        23321, -- 2311.08403 Instant3D: Instant Text-to-3D Generation
        23390, -- 2311.09217 DMV3D: Denoising Multi-View Diffusion using 3D Large Reconstruction Mo
        24036, -- 2311.18635 DiffusionAvatars: Deferred Diffusion for High-fidelity 3D Head Avatars
        24045, -- 2311.18729 Portrait4D: Learning One-Shot 4D Head Avatar Synthesis using Synthetic
        24289, -- 2312.02647 TPA3D: Triplane Attention for Fast Text-to-3D Generation
        24472, -- 2312.04651 VOODOO 3D: Volumetric Portrait Disentanglement for One-Shot 3D Head Re
        24504, -- 2312.05161 TriHuman : A Real-time and Controllable Tri-plane Representation for D
        24773, -- 2312.08882 Neural Video Fields Editing
        24797, -- 2312.09147 Triplane Meets Gaussian Splatting: Fast and Generalizable Single-View
        25257, -- 2312.16837 DiffusionGAN3D: Boosting Text-guided 3D Generation and Domain Adaptati
        25728, -- 2401.06191 TriNeRFLet: A Wavelet Based Triplane NeRF Representation
        25824, -- 2401.07727 HexaGen3D: StableDiffusion is just one step away from Fast and Diverse
        25944, -- 2401.09386 Tri$^{2}$-plane: Thinking Head Avatar via Feature Pyramid
        26005, -- 2401.10215 GPAvatar: Generalizable and Precise Head Avatar from Image(s)
        26137, -- 2401.12175 Template-Free Single-View 3D Human Digitalization with Diffusion-Guide
        26482, -- 2401.17053 BlockFusion: Expandable 3D Scene Generation using Latent Tri-plane Ext
        26606, -- 2402.00867 AToM: Amortized Text-to-Mesh using 2D Diffusion
        28371, -- 2403.02234 3DTopia: Large Text-to-3D Generation Model with Hybrid Diffusion Prior
        28561, -- 2403.05034 CRM: Single Image to 3D Textured Mesh with Convolutional Reconstructio
        28858, -- 2403.09439 3D-SceneDreamer: Text-Driven 3D-Consistent Scene Generation
        28991, -- 2403.11273 BrightDreamer: Generic 3D Gaussian Generative Framework for Fast Text-
        29190, -- 2403.13524 Compress3D: a Compressed Latent Space for 3D Generation from a Single
        29723, -- 2404.00636 Learning to Generate Conditional Tri-plane for 3D-aware Expression Con
        29778, -- 2404.01225 SurMo: Surface-based 4D Motion Modeling for Dynamic Human Rendering
        30006, -- 2404.04319 SpatialTracker: Tracking Any 2D Pixels in 3D Space
        30538, -- 2404.12378 6Img-to-3D: Few-Image Large-Scale Outdoor Driving Scene Reconstruction
        31340, -- 2405.09874 Dual3D: Efficient and Consistent Text-to-3D Generation with Dual-mode
        31625, -- 2405.14832 Direct3D: Scalable Image-to-3D Generation via 3D Latent Diffusion Tran
        31703, -- 2405.15622 LAM3D: Large Image-Point-Cloud Alignment Model for 3D Reconstruction f
        32453, -- 2406.04322 DIRECT-3D: Learning Direct Text-to-3D Generation on Massive Noisy 3D D
        32557, -- 2406.05649 GTR: Improving Large 3D Reconstruction Models through Geometry and Tex
        32989, -- 2406.10373 Wild-GS: Real-Time Novel View Synthesis from Unconstrained Photo Colle
        34334, -- 2407.06191 Tailor3D: Customized 3D Assets Editing and Generation with Dual-Side I
        34377, -- 2407.06938 RodinHD: High-Fidelity 3D Avatar Generation with Diffusion Models
        37608, -- 2410.00890 Flex3D: Feed-Forward 3D Generation with Flexible Reconstruction Model
        38186, -- 2410.07160 TextToon: Real-Time Text Toonify Head Avatar from Single Video
        39090, -- 2410.18355 Real-time 3D-aware Portrait Video Relighting
        40160, -- 2411.12290 SSEditor: Controllable Mask-to-Scene Generation with Diffusion Model
        40292, -- 2411.14762 Efficient Long Video Tokenization via Coordinate-based Patch Reconstru
        40889, -- 2412.02202 3D representation in 512-Byte:Variational tokenizer is the key for aut
        41876, -- 2412.14464 LiftRefine: Progressively Refined View Synthesis from 3D Lifting with
        42609, -- 2501.04374 Instructive3D: Editing Large Reconstruction Models with Text Instructi
        43433, -- 2501.18672 Drag Your Gaussian: Effective Drag-Based Editing with Score Distillati
        45915, -- 2503.08737 Representing 3D Shapes With 64 Latent Vectors for 3D Diffusion Models
        46046, -- 2503.10403 Hyper3D: Efficient 3D Representation via Hybrid Triplane and Octree Fe
        46539, -- 2503.17095 FFaceNeRF: Few-shot Face Editing in Neural Radiance Fields
        46750, -- 2503.19906 AvatarArtist: Open-Domain 4D Avatarization
        46775, -- 2503.20221 TC-GS: Tri-plane based compression for 3D Gaussian Splatting
        46865, -- 2503.21694 Progressive Rendering Distillation: Adapting Stable Diffusion for Inst
        49418, -- 2505.16535 SHaDe: Compact and Consistent Dynamic 3D Reconstruction via Tri-Plane
        52453, -- 2508.15228 Collaborative Multi-Modal Coding for High-Quality 3D Generation
        54771, -- 2512.12751 GenieDrive: Towards Physics-Aware Driving World Model with 4D Occupanc
        67039, -- 2510.08587 EGSTalker: Real-Time Audio-Driven Talking Head Generation with Efficie
        67719, -- 2509.21965 PartSAM: A Scalable Promptable Part Segmentation Model Trained on Nati
        68576, -- 2509.07552 PanoLAM: Large Avatar Model for Gaussian Full-Head Synthesis from One-
        68694, -- 2509.05131 A Scalable Attention-Based Approach for Image-to-3D Texture Mapping
        73886, -- 2503.19191 FDS: Frequency-Aware Denoising Score for Text-Guided Latent Diffusion
        74708, -- 2502.09623 Weight Space Representation Learning on Diverse NeRF Architectures
        76234, -- 2409.20530 Dual Encoder GAN Inversion for High-Fidelity 3D Head Reconstruction fr
        78164, -- 2312.01632 GaussianHead: High-fidelity Head Avatars with Learnable Gaussian Deriv
        86247, -- 2509.16748 HyPlaneHead: Rethinking Tri-plane-like Representations in Full-Head Im
        87939, -- 2412.16919 TAR3D: Creating High-Quality 3D Assets via Next-Part Prediction
        88033, -- 2501.03399 Compression of 3D Gaussian Splatting with Optimized Feature Planes and
        88416, -- 2503.22349 GCRayDiffusion: Pose-Free Surface Reconstruction via Geometric Consist
        90264, -- 2503.16630 TriTex: Learning Texture from a Single Mesh via Triplane Semantic Feat
        90350, -- 2404.03632 Reference-Based 3D-Aware Image Editing with Triplanes
        90494, -- 2503.18107 PanoGS: Gaussian-based Panoptic Segmentation for 3D Open Vocabulary Sc
        90698, -- 2504.14967 3D Gaussian Head Avatars with Expressive Dynamic Appearances by Compac
        90726, -- 2503.06900 DirectTriGS: Triplane-based Gaussian Splatting Field Representation fo
        93242, -- 2410.23742 Fused-Planes: Why Train a Thousand Tri-Planes When You Can Share?
        94805, -- 2506.00600 SatDreamer360: Multiview-Consistent Generation of Ground-Level Scenes
        94994, -- 2603.05882 CylinderSplat: 3D Gaussian Splatting with Cylindrical Triplanes for Pa
        95281, -- external From Dream to Action: Hierarchical Policy Learning with 3D World Imagi
        97442, -- 2506.12251 Efficient Multi-Camera Tokenization with Triplanes for End-To-End Driv
        104975, -- 2405.15241 Blaze3DM: Integrating Triplane Representation with Diffusion for Solvi
        106786, -- 2511.07819 Human Motion Synthesis in 3D Scenes via Unified Scene Semantic Occupan
        108439, -- 2507.04258 MoReMouse: Monocular Reconstruction of Laboratory Mouse
        112968, -- 2407.13545 DiffuX2CT: Diffusion Learning to Reconstruct CT Images from Biplanar X
        112987, -- 2407.13185 KFD-NeRF: Rethinking Dynamic NeRF with Kalman Filter
        113050, -- 2409.15715 Disentangled Generation and Aggregation for Robust Radiance Fields
        113104, -- 2402.13729 Hybrid Video Diffusion Models with 2D Triplane and 3D Wavelet Represen
        113172, -- external DMiT: Deformable Mipmapped Tri-Plane Representation for Dynamic Scenes
        113321, -- external Loc3Diff: Local Diffusion for 3D Human Head Synthesis and Editing
        113365, -- 2404.03654 RaFE: Generative Radiance Fields Restoration
        113478, -- 2407.15771 Local Occupancy-Enhanced Object Grasping with Multiple Triplanar Proje
        113506, -- 2404.05680 SphereHead: Stable 3D Full-head Synthesis with Spherical Tri-plane Rep
        115594, -- 2403.07773 SemCity: Semantic Scene Generation with Triplane Diffusion
        116072, -- 2312.09866 PLGSLAM: Progressive Neural Scene Represenation with Local to Global B
        116134, -- 2312.06713 TeTriRF: Temporal Tri-Plane Radiance Fields for Efficient Free-Viewpoi
        116504, -- 2403.19473 Benchmarking Implicit Neural Representation and Geometric Rendering in
        116524, -- external 3D-Aware Face Editing via Warping-Guided Latent Direction Learning
        116718, -- 2403.09632 Holo-Relighting: Controllable Volumetric Portrait Relighting from a Si
        117250, -- 2601.12736 KaoLRM: Repurposing Pre-trained Large Reconstruction Models for Parame
        117300, -- 2503.06382 X-LRM: X-ray Large Reconstruction Model for Extremely Sparse-View Comp
        117383, -- external Reconstructing 3D Human-Object Interaction via a Unified Triplane Spac
        117642, -- external TriSplat: Adaptive Triplane for Sparse-View Large-Scale Scene Reconstr
        117761, -- 2607.15806 HybridSim: A Physics–Learning Hybrid Digital Twin for mmWave Human Sen
        117939, -- external TriNLOS: Triplane Representations for Neural Non-Line-of-Sight Imaging
        119900, -- external High-Fidelity Lightweight Mesh Reconstruction from Point Clouds
        120132, -- 2405.00794 Coherent 3D Portrait Video Reconstruction via Triplane Fusion
        120347, -- external PDFactor: Learning Tri-Perspective View Policy Diffusion Field for Mul
        120374, -- external Pose-Guided Temporal Enhancement for Robust Low-Resolution Hand Recons
        120913, -- external CryoKRAQEN: Kernel-Regularized Annealing for Quantized Embedding Netwo
        121840, -- external HumanNOVA: Photorealistic, Universal and Rapid 3D Human Avatar Modelin
        121896, -- external Prospective Dynamic 3D MRI Reconstruction via Latent-Space Motion Trac
        125960, -- external Aligned Delta-Triplane Transformers as Occupancy World Models
        130060  -- external Bridging 1D, 2D, and 3D with Any-to-Any Multimodal Modeling
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
        34017, -- 2407.02040 ScaleDreamer: Scalable Text-to-3D Synthesis with Asynchronous Score Di
        35981, -- 2408.10198 MeshFormer: High-Quality Mesh Generation with 3D-Guided Reconstruction
        46940, -- 2503.22537 LIM: Large Interpolator Model for Dynamic Reconstruction
        63724, -- 2512.13247 STARCaster: Spatio-Temporal AutoRegressive Video Diffusion for Identit
        63812, -- 2512.10947 Towards Efficient and Effective Multi-Camera Encoding for End-to-End D
        115385, -- 2409.08492 Tri-Plane Mamba: Efficiently Adapting Segment Anything Model for 3D Me
        116012  -- 2403.15664 What Do You See in Vehicle? Comprehensive Vision Solution for In-Vehic
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
        2082, -- 1905.03561 D2-Net: A Trainable CNN for Joint Detection and Description of Local F
        2751, -- 1910.14532 AQUALOC: An Underwater Dataset for Visual-Inertial-Pressure Localizati
        2866, -- 1911.11763 SuperGlue: Learning Feature Matching with Graph Neural Networks
        3482, -- 2004.15021 Consistent Video Depth Estimation
        6191, -- 2107.02791 Depth-supervised NeRF: Fewer Views and Faster Training for Free
        11513, -- 2211.12018 Level-S$^2$fM: Structure from Motion on Neural Level Set of Implicit S
        11591, -- 2211.13551 SfM-TTR: Using Structure from Motion for Test-Time Refinement of Singl
        12320, -- 2301.02239 Robust Dynamic Radiance Fields
        13601, -- 2303.05195 Revisiting Rotation Averaging: Uncertainties and Robust Losses
        15572, -- 2305.08810 AutoRecon: Automated 3D Object Discovery and Reconstruction
        17181, -- 2306.05410 LU-NeRF: Scene and Pose Estimation by Synchronizing Local Unposed NeRF
        17458, -- 2306.09012 Yes, we CANN: Constrained Approximate Nearest Neighbors for local feat
        17465, -- 2306.09109 NAVI: Category-Agnostic Image Collections with High-Quality 3D Shape a
        17816, -- 2306.15667 PoseDiffusion: Solving Pose Estimation via Diffusion-aided Bundle Adju
        18716, -- 2307.15055 PointOdyssey: A Large-Scale Synthetic Dataset for Long-Term Point Trac
        20128, -- 2309.02420 Doppelgangers: Learning to Disambiguate Images of Similar Structures
        22342, -- 2310.14364 A Quantitative Evaluation of Dense 3D Reconstruction of Sinus Anatomy
        23936, -- 2311.17245 LightGaussian: Unbounded 3D Gaussian Compression with 15x Reduction an
        24113, -- 2312.00451 FSGS: Real-Time Few-shot View Synthesis using Gaussian Splatting
        24464, -- 2312.04563 Visual Geometry Grounded Deep Structure From Motion
        24639, -- 2312.06741 Gaussian Splatting SLAM
        25911, -- 2401.08937 ICON: Incremental CONfidence for Joint Pose and Radiance Field Optimiz
        27816, -- 2402.14650 GaussianPro: 3D Gaussian Splatting with Progressive Propagation
        28793, -- 2403.08640 Refractive COLMAP: Refractive Structure-from-Motion Revisited
        29677, -- 2403.20309 InstantSplat: Sparse-view SfM-free Gaussian Splatting in Seconds
        30561, -- 2404.12547 Evaluating Alternatives to SFM Point Cloud Initialization for Gaussian
        30649, -- 2404.14351 Scene Coordinate Reconstruction: Posing of Image Collections via Incre
        30709, -- 2404.15259 FlowMap: High-Quality Camera Poses, Intrinsics, and Depth via Gradient
        31368, -- 2405.10320 Toon3D: Seeing Cartoons from New Perspectives
        32306, -- 2406.02509 CamCo: Camera-Controllable 3D-Consistent Image-to-Video Generation
        32608, -- 2406.06216 Lighting Every Darkness with 3DGS: Fast Training and Real-Time Renderi
        33161, -- 2406.11819 MegaScenes: Scene-Level View Synthesis at Scale
        33722, -- 2406.18198 VDG: Vision-Only Dynamic Gaussian for Driving Simulation
        34443, -- 2407.07860 Controlling Space and Time with Diffusion Models
        34618, -- 2407.10102 3DEgo: 3D Editing on the Go!
        36571, -- 2409.02581 Object Gaussian for Monocular 6D Pose Estimation from Sparse Views
        36995, -- 2409.11307 GS-Net: Generalizable Plug-and-Play 3D Gaussian Splatting Module
        39143, -- 2410.18956 Large Spatial Model: End-to-end Unposed Images to Semantic 3D
        40060, -- 2411.10546 The Oxford Spires Dataset: Benchmarking Large-Scale LiDAR-Visual Local
        41081, -- 2412.04463 MegaSaM: Accurate, Fast, and Robust Structure and Motion from Casual D
        43644, -- 2502.02283 GP-GS: Gaussian Processes for Enhanced Gaussian Splatting
        43924, -- 2502.06367 FOCUS - Multi-View Foot Reconstruction From Synthetically Trained Dens
        45275, -- 2503.00737 Multi-Cali Anything: Dense Feature Multi-Frame Structure-from-Motion f
        45715, -- 2503.06660 AxisPose: Model-Free Matching-Free Single-Shot 6D Object Pose Estimati
        46343, -- 2503.14483 Multi-view Reconstruction via SfM-guided Monocular Depth Estimation
        46562, -- 2503.17486 ProtoGS: Efficient and High-Quality Rendering with 3D Gaussian Prototy
        46997, -- 2503.23282 AnyCam: Learning to Recover Camera Poses and Intrinsics from Casual Vi
        48017, -- 2504.15376 Towards Understanding Camera Motions in Any Video
        48120, -- 2504.17788 Dynamic Camera Poses and Where to Find Them
        48545, -- 2505.05473 DiffusionSfM: Predicting Structure and Motion via Ray Origin and Endpo
        51842, -- 2507.08448 Review of Feed-forward 3D Reconstruction: From DUSt3R to VGGT
        53021, -- 2509.25191 VGGT-X: When VGGT Meets Dense Novel View Synthesis
        58493, -- 2604.04931 LoMa: Local Feature Matching Revisited
        58989, -- 2603.23192 GTLR-GS: Geometry-Texture Aware LiDAR-Regularized 3D Gaussian Splattin
        59078, -- 2603.20714 The Role and Relationship of Initialization and Densification in 3D Ga
        59556, -- 2603.11174 GGPT: Geometry Grounded Point Transformer
        59687, -- 2603.08055 Speed3R: Sparse Feed-forward 3D Reconstruction Models
        60192, -- 2602.23645 BuildAnyPoint: 3D Building Structured Abstraction from Diverse Point C
        61026, -- 2602.07891 Scalable Adaptation of 3D Geometric Foundation Models via Weak Supervi
        61239, -- 2602.04672 AGILE: Hand-Object Interaction Reconstruction from Video via Agentic G
        63914, -- 2512.08930 Selfi: Self Improving Reconstruction Engine via 3D Geometric Feature A
        64536, -- 2511.20343 AMB3R: Accurate Feed-forward Metric-scale 3D Reconstruction with Backe
        64662, -- 2511.18559 C3Po: Cross-View Cross-Modality Correspondence by Pointmap Prediction
        64837, -- 2511.15153 SceneEdited: A City-Scale Benchmark for 3D HD Map Updating via Image-G
        66222, -- 2510.16438 LightGlueStick: a Fast and Robust Glue for Joint Point-Line Matching
        66265, -- 2510.15271 CuSfM: CUDA-Accelerated Structure-from-Motion
        66390, -- 2510.13310 InstantSfM: Fully Sparse and Parallel Structure-from-Motion
        68304, -- 2509.13414 MapAnything: Universal Feed-Forward Metric 3D Reconstruction
        69207, -- 2508.17972 SAIL-Recon: Large SfM by Augmenting Scene Regression with Localization
        70887, -- 2507.16406 Sparse-View 3D Reconstruction: Recent Advances and Open Challenges
        71621, -- 2506.23611 AttentionGS: Towards Initialization-Free 3D Gaussian Splatting via Str
        71735, -- 2506.21629 ICP-3DGS: SfM-free 3D Gaussian Splatting for Large-scale Unbounded Sce
        73489, -- 2504.13204 EDGS: Eliminating Densification for Efficient Convergence of 3DGS
        73571, -- 2504.08252 Stereophotoclinometry Revisited
        73696, -- 2504.04294 3R-GS: Best Practice in Optimizing Camera Poses Along with 3DGS
        74359, -- 2503.00853 MTReD: 3D Reconstruction Dataset for Fly-over Videos of Maritime Domai
        74953, -- 2502.01297 XR-VIO: High-precision Visual Inertial Odometry with Fast Initializati
        75088, -- 2501.14914 Light3R-SfM: Towards Feed-forward Structure-from-Motion
        76739, -- 2407.12207 NeuSurfEmb: A Complete Pipeline for Dense Correspondence-based 6D Obje
        77419, -- 2404.11358 DeblurGS: Gaussian Splatting for Camera Motion Blur
        79732, -- 2209.08690 A Hybrid Cable-Driven Robot for Non-Destructive Leafy Plant Monitoring
        84232, -- 2511.19172 MetroGS: Efficient and Stable Reconstruction of Geometrically Accurate
        84266, -- 2511.21565 UAVLight: A Benchmark for Illumination-Robust 3D Reconstruction in Unm
        84336, -- 2512.04012 Emergent Outlier View Rejection in Visual Geometry Grounded Transforme
        84518, -- 2602.14929 WRIVINDER: Towards Spatial Intelligence for Geo-locating Ground Images
        84580, -- 2602.20630 From Pairs to Sequences: Track-Aware Policy Gradients for Keypoint Det
        84610, -- 2602.21963 Global-Aware Edge Prioritization for Pose Graph Initialization
        84626, -- 2602.22639 QuadSync: Quadrifocal Tensor Synchronization via Tucker Decomposition
        84762, -- 2603.05330 Dark3R: Learning Structure from Motion in the Dark
        85175, -- 2603.27542 MV-RoMa: From Pairwise Matching into Multi-View Track Reconstruction
        85400, -- 2604.16540 PoInit-of-View: Poisoning Initialization of Views Transfers Across Mul
        85448, -- 2604.22202 ArchSym: Detecting 3D-Grounded Architectural Symmetries in the Wild
        85539, -- 2605.10204 3DReflecNet: A Large-Scale Dataset for 3D Reconstruction of Reflective
        85547, -- 2605.12774 WildPose: A Unified Framework for Robust Pose Estimation in the Wild
        85572, -- 2605.17014 RHINO: Reconstructing Human Interactions with Novel Objects from Monoc
        86375, -- 2509.23991 RPG360: Robust 360 Depth Estimation with Perspective Foundation Models
        87042, -- 2505.23756 Rooms from Motion: Un-posed Indoor 3D Object Detection as Localization
        87613, -- 2504.09129 A Constrained Optimization Approach for Gaussian Splatting from Coarse
        87629, -- 2502.12545 IM360: Large-scale Indoor Mapping with 360 Cameras
        87920, -- 2507.03306 MGSfM: Multi-Camera Geometry Driven Global Structure-from-Motion
        88032, -- 2506.22069 Single-Scanline Relative Pose Estimation for Rolling Shutter Cameras
        88142, -- 2503.04351 PLMP - Point-Line Minimal Problems for Projective SfM
        88508, -- 2411.18650 RoMo: Robust Motion Segmentation Improves Structure from Motion
        90208, -- 2503.17093 ColabSfM: Collaborative Structure-from-Motion by Point Cloud Registrat
        90222, -- 2503.01661 MUSt3R: Multi-view Network for Stereo 3D Reconstruction
        90303, -- 2412.01553 SfM-Free 3D Gaussian Splatting via Hierarchical Training
        90384, -- 2411.12592 SPARS3R: Semantic Prior Alignment and Regularization for Sparse 3D Rec
        90385, -- 2503.07135 VidBot: Learning Generalizable 3D Actions from In-the-Wild 2D Human Vi
        90398, -- 2505.08013 RDD: Robust Feature Detector and Descriptor using Deformable Transform
        90855, -- 2504.20378 Sparse2DGS: Geometry-Prioritized Gaussian Splatting for Surface Recons
        92546, -- 2606.03577 Eliciting Complex Spatial Reasoning in MLLMs through Wide-Baseline Mat
        95873, -- 2509.06685 MOGS: Monocular Object-Guided Gaussian Splatting in Large Scenes
        95920, -- 2510.01665 Non-Rigid Structure-From-Motion Via Differential Geometry with Recover
        96132, -- 2601.05805 InsSo3D: Inertial Navigation System and 3D Sonar SLAM for Turbid Envir
        96515, -- 2512.07969 Sparse Variable Projection in Robotic Perception: Exploiting Separable
        96518, -- 2502.02657 SiLVR: Scalable Lidar-Visual Radiance Field Reconstruction with Uncert
        96672, -- external PG-Match: A Pose-Guided Generalizable Framework for Semi-Dense Feature
        97208, -- external SAVMap: Structure-Aided Visual Mapping of Large-Scale 2.5D Manhattan W
        97493, -- 2602.03209 Depth Completion in Unseen Field Robotics Environments Using Extremely
        97548, -- 2510.15467 MRASfM: Multi-Camera Reconstruction and Aggregation through Structure-
        97678, -- external Mapping Pamir: Multi-Session Visual/Inertial SLAM and 3D Reconstructio
        103900, -- 2606.27071 PanoImager: Geometry-Guided Novel View Synthesis and Reconstruction fr
        105154, -- 2503.07204 Endo-FASt3r: Endoscopic Foundation model Adaptation for Structure from
        109481, -- external Structure-from-Motion Revisited
        109482, -- 2407.20219 Global Structure-from-Motion Revisited
        109873, -- 2409.02310 Geometry-Aware Feature Matching for Large-Scale Structure from Motion
        109877, -- 2409.19152 MASt3R-SfM: A Fully-Integrated Solution for Unconstrained Structure-fr
        112379, -- external A Direct Approach to Viewing Graph Solvability
        112506, -- 2408.10739 TrackNeRF: Bundle Adjusting NeRF from Sparse and Noisy Views via Featu
        112510, -- 2405.05079 Power Variable Projection for Initialization-Free Large-Scale Bundle A
        112860, -- 2409.19811 Robust Incremental Structure-from-Motion with Hybrid Features
        112871, -- external Synchronization of Projective Transformations
        112915, -- 2410.12763 Gravity-aligned Rotation Averaging with Circular Regression
        113067, -- external Resolving Scale Ambiguity in Multi-view 3D Reconstruction using Dual-P
        113236, -- 2403.20032 HO-Gaussian: Hybrid Optimization of 3D Gaussian Splatting for Urban Sc
        113580, -- 2403.04926 BAGS: Blur Agnostic Gaussian Splatting through Multi-Scale Kernel Mode
        113604, -- external Revisit Self-supervision with Local Structure-from-Motion
        113643, -- external Self-Supervised Underwater Caustics Removal and Descattering via Deep
        114890, -- external EndoSelf: Self-Supervised Monocular 3D Scene Reconstruction of Deforma
        114952, -- 2407.02918 Free-SurGS: SfM-Free 3D Gaussian Splatting for Surgical Scene Reconstr
        115554, -- external Revisiting Global Translation Estimation with Feature Tracks
        115763, -- 2404.11590 A Subspace-Constrained Tyler's Estimator and its Applications to Struc
        115908, -- 2407.04260 Efficient Detection of Long Consistent Cycles and its Application to D
        115951, -- external Leveraging Camera Triplets for Efficient and Accurate Structure-from-M
        116114, -- 2403.17537 NeRF-HuGS: Improved Neural Radiance Fields in Non-static Scenes Using
        116335, -- external Projecting Trackable Thermal Patterns for Dynamic Computer Vision
        116384, -- external Efficient Privacy-Preserving Visual Localization Using 3D Ray Clouds
        116385, -- 2312.05889 SuperPrimitive: Scene Reconstruction at a Primitive Level
        116446, -- 2308.15984 Learning Structure-from-Motion with Graph Attention Networks
        116489, -- external PanoPose: Self-supervised Relative Pose Estimation for Panoramic Image
        116625, -- 2405.04309 Non-Rigid Structure-from-Motion: Temporally-Smooth Procrustean Alignme
        116886, -- 2306.15669 Detector-Free Structure from Motion
        117302, -- 2602.18906 Marginalized Bundle Adjustment: Multi-View Camera Pose from Monocular
        117328, -- 2603.18401 Pixel-Accurate Epipolar Guided Matching
        117340, -- 2505.04612 FastMap: Revisiting Structure from Motion through First-Order Optimiza
        117348, -- external C3PO: Canonicalization of 3D Pose from Partial Views with Generalizabl
        117350, -- 2503.08142 A Framework for Reducing the Complexity of Geometric Vision Problems a
        117555, -- 2608.23549 FixAnything: 3D-Consistent Rendering Refinement via Video Generative P
        117603, -- 2604.14302 Geometrically Consistent Multi-View Scene Generation from Freehand Ske
        117658, -- 2605.14880 Denoising-GS: Gaussian Splatting with Spatial-aware Denoising
        118242, -- 2607.03855 PRISM3D: Probabilistic Refinement and Robust Initialization for Physic
        118253, -- external Learning Global Camera Poses from Noisy View-Graphs for Structure from
        118269, -- external VideoSfM: Exploiting Temporal Structure for Video-Based Structure-from
        118349, -- 2606.31077 AnyMatch: Supercharging Universal Multi-Modal Image Matching with Larg
        119326, -- 2512.05398 The Dynamic Prior: Understanding 3D Structures for Casual Dynamic Vide
        119567, -- 2607.09503 What VGGT Knows About Overlap: Probing Geometric Foundation Models for
        119819, -- 2308.08479 DeDoDe: Detect, Don't Describe - Describe, Don't Detect for Local Feat
        119884, -- external Shading Meets Motion: Self-supervised Indoor 3D Reconstruction Via Sim
        119952, -- external Learning to Filter Outlier Edges in Global SfM
        120099, -- 2501.14277 Dense-SfM: Structure from Motion with Dense Consistent Matching
        120115, -- 2504.16499 PRaDA: Projective Radial Distortion Averaging
        120124, -- external EAP-GS: Efficient Augmentation of Pointcloud for 3D Gaussian Splatting
        120154, -- 2504.00219 LITA-GS: Illumination-Agnostic Novel View Synthesis via Reference-Free
        120205, -- external AnyMap: Learning a General Camera Model for Structure-from-Motion with
        120315, -- external IndoorGS: Geometric Cues Guided Gaussian Splatting for Indoor Scene Re
        120450, -- external Structure-from-Motion with a Non-Parametric Camera Model
        120487, -- 2501.14945 MATCHA: Towards Matching Anything
        120551, -- 2412.17806 Reconstructing People, Places, and Cameras
        120558, -- 2412.05826 Doppelgangers++: Improved Visual Disambiguation with Geometric 3D Feat
        120565, -- 2504.20040 MP-SfM: Monocular Surface Priors for Robust Structure-from-Motion
        120685, -- external PhysIR-Splat: Physically Consistent Thermal Infrared Radiative Transfe
        121033, -- external ORBIT: Benchmarking SfM in the Wild with 360deg Video
        121091, -- external Solvability of the Viewing Graph Under the Affine Camera Model
        121111, -- external 2D-LFM: Lifting Foundation Model without 3D Supervision
        121282, -- external Learning Scene Coordinate Reconstruction from Unposed Images via Pose
        121346, -- external BA-GS: Bayesian Adaptive Gaussian Splatting for SFM-Free 3D Reconstruc
        121506, -- 2605.26103 Global Structure-from-Motion Meets Feedforward Reconstruction
        121551, -- external Simple but Effective Triplet-Based Compression Strategies for Compact
        121685, -- external Parallel Rigidity Matters for Bundle Adjustment
        121932, -- external A Dataset for Benchmarking Image-Based Localization
        124123, -- 2309.08927 DynaMoN: Motion-Aware Fast and Robust Camera Localization for Dynamic
        124683, -- external Scaffold3D: SfM-Conditioned Pointmap Prediction for Multi-View 3D Reco
        125151, -- external WaterDescatterGS: Diverse Underwater 3D Scene Reconstruction Using Gau
        126160, -- 2606.30058 Emergence of a Shared Canonical Object Frame from In-the-Wild Videos
        126606, -- 2604.22686 SS3D: End2End Self-Supervised 3D from Web Videos
        127231, -- external Certifiably Optimal Robust Angular Synchronization
        127290, -- external 3D Consistency Tokens
        129856, -- external PosePlaner: Denoising Any Feedforward Pose Predictor from Pairwise Pla
        130257, -- external Generative Structure from Motion with Native 3D Diffusion
        130584, -- 2607.09225 Glob3R: Global Structure-from-Motion with 3D Foundation Models
        131565, -- 2001.06659 Multi-View Photometric Stereo: A Robust Solution and Benchmark Dataset
        131852, -- 2610.32976 FlexGlue: Sparse-to-Dense Feature Matching and Visual Disambiguation
        131867  -- 2611.02857 Solv3R: 3D Looped Transformer as a Multi-view Solver
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
        14082, -- 2303.13791 Progressively Optimized Local Radiance Fields for Robust View Synthesi
        18423, -- 2307.10206 NEAT: Distilling 3D Wireframes from Neural Attraction Fields
        21464, -- 2310.03704 Pose-Free Generalizable Rendering Transformer
        24690, -- 2312.07504 COLMAP-Free 3D Gaussian Splatting
        32436, -- 2406.04251 Improving Gaussian Splatting with Localized Points Management
        38512, -- 2410.11187 Multiview Scene Graph
        41521, -- 2412.09982 SplineGS: Robust Motion-Adaptive Spline for Real-Time Dynamic 3D Gauss
        44868, -- 2502.16779 Unposed Sparse Views Room Layout Reconstruction in the Age of Pretrain
        50572, -- 2506.04225 Voyager: Long-Range and World-Consistent Video Diffusion for Explorabl
        51381, -- 2506.18792 ViDAR: Video Diffusion-Aware 4D Reconstruction From Monocular Inputs
        81873, -- 1811.05304 Self-Supervised Learning of Depth and Camera Motion from 360° Videos
        85066, -- 2603.23324 Pose-Free Omnidirectional Gaussian Splatting for 360-Degree Videos wit
        85446, -- 2604.22160 GenMatter: Perceiving Physical Objects with Generative Matter Models
        105150, -- 2504.03198 Endo3R: Unified Online Reconstruction from Dynamic Monocular Endoscopi
        109353, -- 2608.06117 Confidence matters: Leveraging Multi-view Geometric Priors for GS-base
        116676, -- 2404.07933 Boosting Self-Supervision for Single-View Scene Completion via Knowled
        119780, -- 2406.08463 Self-Supervised Learning of Neural Implicit Feature Fields for Camera
        120034, -- external Hand-held Object Reconstruction from RGB Video with Dynamic Interactio
        121288, -- 2604.00548 Reliev3R: Relieving Feed-forward 3D Reconstruction from Multi-View Geo
        122612, -- 2609.39627 Introduction to Computer Vision
        123803  -- 2205.04565 Is my Depth Ground-Truth Good Enough? HAMMER -- Highly Accurate Multi-
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
        2849, -- 1911.10127 BlendedMVS: A Large-scale Dataset for Generalized Multi-view Stereo Ne
        4655, -- 2012.01411 PatchmatchNet: Learned Multi-View Patchmatch Stereo
        5609, -- 2104.14540 The Temporal Opportunist: Self-Supervised Multi-Frame Monocular Depth
        7459, -- 2112.05126 IterMVS: Iterative Probability Estimation for Efficient Multi-View Ste
        8950, -- 2205.02836 Neural 3D Scene Reconstruction with the Manhattan-world Assumption
        13366, -- 2302.14340 HelixSurf: A Robust and Efficient Neural Implicit Surface Learning of
        13644, -- 2303.06042 MVImgNet: A Large-scale Dataset of Multi-view Images
        13681, -- 2303.06615 Iterative Geometry Encoding Volume for Stereo Matching
        13853, -- 2303.09758 Hierarchical Prior Mining for Non-local Multi-View Stereo
        14325, -- 2303.17712 S-VolSDF: Sparse Multi-View Stereo Regularization of Neural Implicit S
        15046, -- 2304.14633 CVRecon: Rethinking 3D Geometric Feature Learning For Neural Reconstru
        15402, -- 2305.06036 FusionDepth: Complement Self-Supervised Monocular Depth Estimation wit
        15660, -- 2305.10320 CostFormer:Cost Transformer for Cost Aggregation in Multi-view Stereo
        17330, -- 2306.07437 Instant Multi-View Head Capture through Learnable Registration
        17547, -- 2306.10003 C2F2NeUS: Cascade Cost Frustum Fusion for High Fidelity and Generaliza
        18359, -- 2307.09160 Constraining Depth Map Geometry for Multi-View Stereo: A Dual-Depth Ap
        19080, -- 2308.04826 WaveNeRF: Wavelet-based Generalizable Neural Radiance Fields
        19339, -- 2308.08715 V-FUSE: Volumetric Depth Map Fusion with Long-Range Constraints
        21637, -- 2310.05717 STOPNet: Multiview-based 6-DoF Suction Detection for Transparent Objec
        22830, -- 2311.00134 Joint Depth Prediction and Semantic Segmentation with Multi-View SAM
        25101, -- 2312.14132 DUSt3R: Geometric 3D Vision Made Easy
        25166, -- 2312.15238 NoPose-NeuS: Jointly Optimizing Camera Poses with Neural Implicit Surf
        26105, -- 2401.11673 MVSFormer++: Revealing the Devil in Transformer's Details for Multi-Vi
        26298, -- 2401.14354 Learning Robust Generalizable Radiance Field with Visibility and Featu
        27816, -- 2402.14650 GaussianPro: 3D Gaussian Splatting with Progressive Propagation
        29049, -- 2403.11899 GNeRP: Gaussian-guided Neural Reconstruction of Reflective Objects wit
        30257, -- 2404.07992 GoMVS: Geometrically Consistent Cost Aggregation for Multi-View Stereo
        34963, -- 2407.14257 SparseCraft: Few-Shot Neural Reconstruction through Stereopsis Guided
        35077, -- 2407.15848 BoostMVSNeRFs: Boosting MVS-based NeRFs to Generalizable View Synthesi
        40060, -- 2411.10546 The Oxford Spires Dataset: Benchmarking Large-Scale LiDAR-Visual Local
        40651, -- 2411.19102 360Recon: An Accurate Reconstruction Method Based on Depth Fusion from
        40681, -- 2411.19454 GausSurf: Geometry-Guided 3D Gaussian Splatting for Surface Reconstruc
        40861, -- 2412.01821 World-consistent Video Diffusion with Explicit 3D Modeling
        41269, -- 2412.06974 MV-DUSt3R+: Single-Stage Scene Reconstruction from Sparse Views In 2 S
        43439, -- 2501.18804 Zero-Shot Novel View and Depth Synthesis with Multi-View Geometric Dif
        46343, -- 2503.14483 Multi-view Reconstruction via SfM-guided Monocular Depth Estimation
        48376, -- 2505.02175 SparSplat: Fast Multi-View Reconstruction with Generalizable 2D Gaussi
        50554, -- 2506.04115 Multi-view Surface Reconstruction Using Normal and Reflectance Cues
        51842, -- 2507.08448 Review of Feed-forward 3D Reconstruction: From DUSt3R to VGGT
        58466, -- 2604.04925 SimpleProc: Fully Procedural Synthetic Data from Simple Rules for Mult
        60316, -- 2602.22025 Olbedo: An Albedo and Shading Aerial Dataset for Large-Scale Outdoor E
        60381, -- 2602.19766 One2Scene: Geometric Consistent Explorable 3D Scene Generation from a
        64426, -- 2511.22459 Gaussians on Fire: High-Frequency Reconstruction of Flames
        64451, -- 2511.21945 AmodalGen3D: Generative Amodal 3D Object Reconstruction from Sparse Un
        65051, -- 2511.10560 OmniVGGT: Omni-Modality Driven Visual Geometry Grounded
        67848, -- 2509.20607 Reflect3r: Single-View 3D Stereo Reconstruction Aided by Mirror Reflec
        68304, -- 2509.13414 MapAnything: Universal Feed-Forward Metric 3D Reconstruction
        69310, -- 2508.16433 HAMSt3R: Human-Aware Multi-view Stereo 3D Reconstruction
        70764, -- 2507.18541 Unposed 3DGS Reconstruction with Probabilistic Procrustes Mapping
        70887, -- 2507.16406 Sparse-View 3D Reconstruction: Recent Advances and Open Challenges
        79885, -- 2206.10360 Enhancing Multi-view Stereo with Contrastive Matching and Weighted Foc
        80340, -- 2112.02338 Generalized Binary Search Network for Highly-Efficient Multi-View Ster
        81405, -- 2003.10432 Atlas: End-to-End 3D Scene Reconstruction from Posed Images
        84266, -- 2511.21565 UAVLight: A Benchmark for Illumination-Robust 3D Reconstruction in Unm
        84731, -- 2603.03765 LiDAR Prompted Spatio-Temporal Multi-View Stereo for Autonomous Drivin
        87803, -- 2508.04297 MuGS: Multi-Baseline Generalizable Gaussian Splatting Reconstruction
        88215, -- 2507.11333 MonoMVSNet: Monocular Priors Guided Multi-View Stereo Network
        90501, -- 2503.16964 DroneSplat: 3D Gaussian Splatting for Robust 3D Reconstruction from In
        90690, -- 2503.22430 MVSAnywhere: Zero-Shot Multi-View Stereo
        90849, -- 2503.17316 Pow3R: Empowering Unconstrained 3D Reconstruction with Camera and Scen
        90855, -- 2504.20378 Sparse2DGS: Geometry-Prioritized Gaussian Splatting for Surface Recons
        95302, -- external PIPS: Planar Instance 3D Reconstruction Leveraging Planar Structural P
        96920, -- external High-Quality Sparse-View Gaussian Splatting without Ground-Truth Camer
        97298, -- external ActMVS: Active Scene Reconstruction with Monocular Multi-View Stereo
        97327, -- external Multi-View Stereo with Geometric Encoding for Large-Scale Dense Scene
        103904, -- external A Multi-View Stereo Benchmark with High-Resolution Images and Multi-Ca
        103908, -- external Deep Blending for Free-Viewpoint Image-Based Rendering
        109468, -- 1804.02505 MVSNet: Depth Inference for Unstructured Multi-view Stereo
        109469, -- 1904.08103 Multi-Scale Geometric Consistency Guided Multi-View Stereo
        109470, -- 1912.11744 Planar Prior Assisted PatchMatch Multi-View Stereo
        109471, -- external Large Scale Multi-view Stereopsis Evaluation
        109472, -- 2208.02541 MVSFormer: Multi-View Stereo by Learning Robust Image Features and Tem
        109473, -- 2304.13614 Multi-View Stereo Representation Revisit: Region-Aware MVSNet
        109474, -- 2309.17218 When Epipolar Constraint Meets Non-local Operators in Multi-View Stere
        109475, -- 2310.19583 GC-MVSNet: Multi-View, Multi-Scale, Geometrically-Consistent Multi-Vie
        109476, -- 2412.20328 Dual-Level Precision Edges Guided Multi-View Stereo with Accurate Plan
        109483, -- external Pixelwise View Selection for Unstructured Multi-View Stereo
        109484, -- external GeoMVSNet: Learning Multi-View Stereo With Geometry Perception
        109485, -- external Adaptive Patch Deformation for Textureless-Resilient Multi-View Stereo
        109487, -- 1912.06378 Cascade Cost Volume for High-Resolution Multi-View Stereo and Stereo M
        109488, -- 1902.10556 Recurrent MVSNet for High-resolution Multi-view Stereo Depth Inference
        109489, -- 2111.14600 TransMVSNet: Global Context-aware Multi-view Stereo Network with Trans
        109490, -- 2201.01501 Rethinking Depth Estimation for Multi-View Stereo: A Unified Represent
        112578, -- 2405.12218 MVSGaussian: Fast Generalizable Gaussian Splatting Reconstruction from
        113017, -- 2409.14316 MVPGS: Excavating Multi-view Priors for Gaussian Splatting from Sparse
        113067, -- external Resolving Scale Ambiguity in Multi-view 3D Reconstruction using Dual-P
        113217, -- 2408.02079 Improving Neural Surface Reconstruction with Feature Priors from Multi
        113296, -- external "Smoothness, Synthesis, and Sampling: Re-thinking Unsupervised Multi-V
        113466, -- 2406.18387 DoubleTake: Geometry Guided Depth Estimation
        113995, -- 2511.01315 MVSMamba: Multi-View Stereo with State Space Model
        115662, -- 2306.00519 DiffInDScene: Diffusion-based High-Quality 3D Indoor Scene Generation
        115848, -- external MVCPS-NeuS: Multi-view Constrained Photometric Stereo for Neural Surfa
        116015, -- 2404.06842 MoCha-Stereo: Motif Channel Attention Network for Stereo Matching
        116514, -- 2406.07111 NeRSP: Neural 3D Reconstruction for Reflective Objects with Sparse Pol
        116920, -- 2311.12754 SelfOcc: Self-Supervised Vision-Based 3D Occupancy Prediction
        117271, -- 2601.12481 NeuralFur: Animal Fur Reconstruction from Multi-view Images
        117280, -- 2511.03950 Improving Multi-View Reconstruction via Texture-Guided Gaussian-Mesh J
        117298, -- external Neural 4D Scene Reconstruction with Multiple One-Shot Scanning Systems
        117301, -- 2602.07860 Recovering 3D Shapes from Ultra-Fast Motion-Blurred Images
        117336, -- 2412.05771 Prism: Semi-Supervised Multi-View Stereo with Monocular Structure Prio
        118349, -- 2606.31077 AnyMatch: Supercharging Universal Multi-Modal Image Matching with Larg
        119777, -- external Addressing Low-Shot MVS by Detecting and Completing Planar Surfaces
        121017, -- external SPE-MVS: Spatial Position Encoding Enhanced Multi-View Stereo with Mon
        121829, -- 2510.09364 VAD-GS: Visibility-Aware Densification for 3D Gaussian Splatting in Dy
        123911, -- 2610.28284 HRoPE: Homography Relative Positional Encoding
        125029, -- external BridgeMVS: Bridging Multi-View Stereo and Monodepth via Bidirectional
        128500  -- external Sequence-to-Sequence Modeling with Camera-Induced Priors for Multi-Vie
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
        11837, -- 2212.03267 NeRDi: Single-View NeRF Synthesis with Language-Guided Diffusion as Ge
        14248, -- 2303.16447 Multi-View Azimuth Stereo via Tangent Space Consistency
        15733, -- 2305.11167 MVPSNet: Fast Generalizable Multi-view Photometric Stereo
        19279, -- 2308.07868 ObjectSDF++: Improved Object-Compositional Neural Implicit Surfaces
        20949, -- 2309.15164 3D Reconstruction with Generalizable Neural Fields using Scene Priors
        32179, -- 2406.00440 Topo4D: Topology-Preserving Gaussian Splatting for High-Fidelity 4D He
        37212, -- 2409.15041 AIM 2024 Sparse Neural Rendering Challenge: Dataset and Benchmark
        41697, -- 2412.12093 CAP4D: Creating Animatable 4D Portrait Avatars with Morphable Multi-Vi
        46262, -- 2503.13385 Scale Efficient Training for Large Datasets
        50572, -- 2506.04225 Voyager: Long-Range and World-Consistent Video Diffusion for Explorabl
        51872, -- 2507.10265 Kaleidoscopic Background Attack: Disrupting Pose Estimation with Multi
        80053, -- 2204.09341 OutCast: Outdoor Single-image Relighting with Cast Shadows
        88310, -- 2509.01469 Im2Haircut: Single-view Strand-based Hair Reconstruction for Human Ava
        106621, -- 2511.22704 Splat-SAP: Feed-Forward Gaussian Splatting for Human-Centered Scene wi
        116414  -- 2404.13541 Generalizable Novel-View Synthesis using a Stereo Camera
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
        11857, -- 2212.04089 Editing Models with Task Arithmetic
        15885, -- 2305.12827 Task Arithmetic in the Tangent Space: Improved Editing of Pre-Trained
        21366, -- 2310.02575 AdaMerging: Adaptive Model Merging for Multi-Task Learning
        22217, -- 2310.12808 Model Merging by Uncertainty-Based Gradient Matching
        23404, -- 2311.09344 Language and Task Arithmetic with Parameter-Efficient Layers for Zero-
        23650, -- 2311.13171 ComPEFT: Compression for Communicating Parameter Efficient Updates via
        24582, -- 2312.06173 Concrete Subspace Learning based Interference Elimination for Multi-ta
        26569, -- 2402.00433 Merging Multi-Task Models via Weight-Ensembling Mixture of Experts
        27537, -- 2402.11746 Language Models are Homer Simpson! Safety Re-Alignment of Fine-tuned L
        31249, -- 2405.07813 Localizing Task Information for Improved Model Merging and Compression
        31303, -- 2405.09055 A safety realignment framework via subspace-oriented model fusion for
        32350, -- 2406.02925 Task Arithmetic can Mitigate Synthetic-to-Real Gap in Automatic Speech
        33098, -- 2406.11385 MetaGPT: Merging Large Language Models Using Model Exclusive Task Arit
        33494, -- 2406.15480 On Giant's Shoulders: Effortless Weak to Strong by Dynamic Logits Fusi
        34077, -- 2407.02880 Knowledge Composition using Task Vectors with Learned Anisotropic Scal
        34399, -- 2407.07176 Scaling Up Personalized Image Aesthetic Assessment via Task Vector Cus
        37514, -- 2409.19854 The Construction of Instruction-tuned LLMs for Finance without Instruc
        38050, -- 2410.05583 NegMerge: Consensual Weight Negation for Strong Machine Unlearning
        39658, -- 2411.03055 ATM: Improving Model Merging by Alternating Tuning and Merging
        42411, -- 2501.01230 Modeling Multi-Task Model Merging as Adaptive Projective Gradient Desc
        43787, -- 2502.04411 Mediator: Memory-efficient LLM Merging with Less Parameter Conflicts a
        45371, -- 2503.01874 CABS: Conflict-Aware and Balanced Sparsification for Enhancing Model M
        45737, -- 2503.06921 Task Vector Quantization for Memory-Efficient Model Merging
        46799, -- 2503.20641 Unlocking Efficient Long-to-Short LLM Reasoning with Model Merging
        46913, -- 2503.22178 AdaRank: Adaptive Rank Pruning for Enhanced Model Merging
        47166, -- 2504.01789 OpenThaiGPT 1.6 and R1: Thai-Centric Open Source and Reasoning Large L
        50908, -- 2506.09093 Merging Smarter, Generalizing Better: Enhancing Model Merging on OOD D
        51346, -- 2506.17818 CultureMERT: Continual Pre-Training for Cross-Cultural Music Represent
        51501, -- 2506.21260 DuET: Dual Incremental Object Detection via Exemplar-Free Task Arithme
        52353, -- 2508.09945 VisCodex: Unified Multimodal Code Generation via Merging Vision and Co
        52607, -- 2509.01363 Reasoning Vectors: Transferring Chain-of-Thought Capabilities via Task
        52623, -- 2509.02108 DivMerge: A divergence-based model merging method for multi-tasking
        53429, -- 2510.08047 Pseudo2Real: Task Arithmetic for Pseudo-Label Correction in Automatic
        53821, -- 2510.21223 Model Merging with Functional Dual Anchors
        56679, -- 2603.07534 Accent Vector: Controllable Accent Manipulation for Multilingual TTS W
        57588, -- 2604.16826 Crowded in B-Space: Calibrating Shared Directions for LoRA Merging
        57636, -- 2604.17078 Understanding and Enforcing Weight Disentanglement in Task Arithmetic
        58580, -- 2604.02719 MOMO: Mars Orbital Model Foundation Model for Mars Orbital Application
        58798, -- 2511.21437 A Systematic Study of In-the-Wild Model Merging for Large Language Mod
        58889, -- 2603.25041 AdaLTM: Adaptive Layer-wise Task Vector Merging for Categorical Speech
        59780, -- 2603.06242 DC-Merge: Improving Model Merging with Directional Consistency
        60404, -- 2602.17385 Dataless Weight Disentanglement in Task Arithmetic via Kronecker-Facto
        66616, -- 2510.09915 Enhancing Faithfulness in Abstractive Summarization via Span-Level Fin
        66877, -- 2510.09658 Gradient-Sign Masking for Task Vector Transport Across Pre-Trained Mod
        67360, -- 2509.25712 Expert Merging: Model Merging with Unsupervised Expert Alignment and I
        67593, -- 2509.23381 Guard Vector: Beyond English LLM Guardrails with Task-Vector Compositi
        69337, -- 2508.16082 On Task Vectors and Gradients
        70379, -- 2508.01148 DisTaC: Conditioning Task Vectors via Distillation for Robust Model Me
        71860, -- 2506.16506 Subspace-Boosted Model Merging
        73297, -- 2504.20106 Adaptive Helpfulness-Harmlessness Alignment with Preference Vectors
        75679, -- 2411.18607 Task Arithmetic Through The Lens Of One-Shot Federated Learning
        75690, -- 2412.00081 Task Singular Vectors: Reducing Task Interference in Model Merging
        76524, -- 2408.13656 Localize-and-Stitch: Efficient Model Merging via Sparse Task Arithmeti
        76646, -- 2408.01119 Task Prompt Vectors: Effective Initialization through Multi-Task Soft-
        83135, -- 2605.13030 FeatCal: Feature Calibration for Post-Merging Models
        83402, -- 2605.16882 E-PMQ: Expert-Guided Post-Merge Quantization with Merged-Weight Anchor
        84313, -- 2512.02441 Basis-Oriented Low-rank Transfer for Few-Shot and Test-Time Adaptation
        84841, -- 2603.10526 Sparse Task Vector Mixup with Hypernetworks for Efficient Knowledge Tr
        85755, -- 2510.11268 Exploring and Leveraging Class Vectors for Classifier Editing
        86036, -- 2509.18208 Variational Task Vector Composition
        86801, -- 2505.23859 Towards Minimizing Feature Drift in Model Merging: Layer-wise Task Vec
        87068, -- 2505.22389 Train with Perturbation, Infer after Merging: A Two-Stage Framework fo
        89103, -- 2506.13406 CALM: Consensus-Aware Localized Merging for Multi-Task Learning
        89182, -- 2505.06977 CAT Merging: A Training-Free Approach for Resolving Conflicts in Model
        89374, -- 2505.22697 Update Your Transformer to the Latest Release: Re-Basin of Task Vector
        89866, -- 2503.08099 Whoever Started the interference Should End It: Guiding Data-Free Mode
        91000, -- 2503.14897 When Domain Generalization meets Generalized Category Discovery: An Ad
        91955, -- 2407.07089 Fine-Tuning Attention Modules Only: Enhancing Weight Disentanglement i
        92790, -- 2505.24262 On Fairness of Task Arithmetic: The Role of Task Vectors
        93204, -- 2602.22538 RAIN-Merging: A Gradient-Free Method to Enhance Instruction Following
        94067, -- 2510.04686 How does the optimizer implicitly bias the model merging loss landscap
        94926, -- 2509.21413 Null-Space Filtering for Data-Free Continual Model Merging: Preserving
        99141, -- 2601.21187 FRISM: Fine-Grained Reasoning Injection via Subspace-Level Model Mergi
        99190, -- 2602.05536 When Shared Knowledge Hurts: Spectral Over-Accumulation in Model Mergi
        100452, -- 2606.12498 From Parameters to Feature Space: Task Arithmetic for Backdoor Mitigat
        100906, -- 2602.12952 Transporting Task Vectors across Different Architectures without Train
        100966, -- 2505.10859 Exploring Nonlinear Pathway in Parameter Space for Machine Unlearning
        101661, -- 2606.00511 Saliency-Aware Model Merging
        101926, -- 2605.18993 Distilling Linearized Behavior into Non-linear Fine-Tuning for Effecti
        106212, -- 2605.03096 When Prompts Interact: Assessing Prompt Arithmetic for Deconfounding u
        107549, -- 2511.17987 Escaping Optimization Stagnation: Taking Steps Beyond Task Arithmetic
        110437, -- 2503.05320 To See a World in a Spark of Neuron: Disentangling Multi-Task Interfer
        111809, -- 2505.13270 Distilling a speech and music encoder with task arithmetic
        113325, -- 2401.02094 PILoRA: Prototype Guided Incremental LoRA for Federated Class-Incremen
        118166, -- 2606.22589 Training-Free Task Classification for Multi-Task Model Merging
        118210, -- 2606.30360 On the Vulnerability of Parameter-Level Defenses to Model Merging
        122086, -- 2609.21094 Geometry of Values: Task Vector Composition for Ethical Preference Ali
        125035, -- 2607.03011 Can Model Merging Improve Aggregation in DiLoCo?
        126406, -- 2609.09054 Training-Free Task Vectors for LLM Behavioral Control
        126825, -- 2610.00929 Platonic Task Arithmetic
        127076, -- external MobTA: Bus-Conditioned Zero-Shot Trajectory Generation via Task Arithm
        127494, -- external Transferring Visual Explainability from Self-Explaining to Prediction-
        128102, -- 2605.18904 Dynamic Model Merging Made Slim
        128230, -- 2609.32332 When the Merge Coefficient Stops Mattering: Proximity Regularized Merg
        130267, -- 2605.09879 M2A: Synergizing Mathematical and Agentic Reasoning in Large Language
        131074, -- external Learning Cultural Vectors for Cross-Cultural Generation
        131995  -- 2611.03953 P^2-MOPD: Accelerating Multi-Teacher On-Policy Distillation via Parame
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
        11784, -- 2212.01378 ColD Fusion: Collaborative Descent for Distributed Multitask Finetunin
        11968, -- 2212.07346 Learning useful representations for shifting tasks and distributions
        12134, -- 2212.10445 Model Ratatouille: Recycling Diverse Models for Out-of-Distribution Ge
        12199, -- 2212.12017 OPT-IML: Scaling Language Model Instruction Meta Learning through the
        12902, -- 2302.03202 Exploring the Benefits of Training Expert Language Models over Instruc
        13255, -- 2302.11529 Modular Deep Learning
        13300, -- 2302.12480 Robust Weight Signatures: Gaining Robustness as Easy as Patching Weigh
        13928, -- 2303.11305 SVDiff: Compact Parameter Space for Diffusion Fine-Tuning
        14989, -- 2304.13718 Sparsified Model Zoo Twins: Investigating Populations of Sparsified Ne
        15243, -- 2305.03053 ZipIt! Merging Models from Different Tasks without Training
        15920, -- 2305.13172 Editing Large Language Models: Problems, Methods, and Opportunities
        16034, -- 2305.14122 Transferring Learning Trajectories of Neural Networks
        16797, -- 2306.00958 LIV: Language-Image Representations and Rewards for Robotic Control
        16873, -- 2306.01708 TIES-Merging: Resolving Interference When Merging Models
        17019, -- 2306.03341 Inference-Time Intervention: Eliciting Truthful Answers from a Languag
        17108, -- 2306.04488 Rewarded soups: towards Pareto-optimal alignment by interpolating weig
        17777, -- 2306.14870 Composing Parameter-Efficient Modules with Arithmetic Operations
        17942, -- 2307.00398 ProbVLM: Probabilistic Adapter for Frozen Vision-Language Models
        18075, -- 2307.03374 STG-MTL: Scalable Task Grouping for Multi-Task Learning Using Data Map
        18222, -- 2307.06966 Layer-wise Linear Mode Connectivity
        18607, -- 2307.13269 LoraHub: Efficient Cross-Task Generalization via Dynamic LoRA Composit
        18767, -- 2307.16184 UnIVAL: Unified Model for Image, Video, Audio and Language Tasks
        19716, -- 2308.12462 Overcoming Generic Knowledge Loss with Selective Parameter Update
        20037, -- 2309.00941 Emergent Linear Representations in World Models of Self-Supervised Seq
        20357, -- 2309.06794 Cognitive Mirage: A Review of Hallucinations in Large Language Models
        21104, -- 2309.17410 Can Sensitive Information Be Deleted From LLMs? Objectives for Defendi
        21227, -- 2310.01217 ScaLearn: Simple and Highly Parameter-Efficient Task Transfer by Learn
        21238, -- 2310.01334 Merge, Then Compress: Demystify Efficient SMoE with Hints from Its Rou
        21548, -- 2310.04861 Uncovering hidden geometry in Transformers via disentangling position
        21660, -- 2310.05884 A Meta-Learning Perspective on Transformers for Causal Language Modeli
        21889, -- 2310.08475 Can We Edit Multimodal Large Language Models?
        22115, -- 2310.11324 Quantifying Language Models' Sensitivity to Spurious Features in Promp
        22126, -- 2310.11451 Seeking Neural Nuggets: Knowledge Transfer in Large Language Models fr
        22135, -- 2310.11564 Personalized Soups: Personalized Large Language Model Alignment via Po
        22431, -- 2310.15213 Function Vectors in Large Language Models
        22438, -- 2310.15308 SAM-CLIP: Merging Vision Foundation Models towards Semantic and Spatia
        22987, -- 2311.03099 Language Models are Super Mario: Absorbing Abilities from Homologous M
        23134, -- 2311.05556 LCM-LoRA: A Universal Stable-Diffusion Acceleration Module
        23197, -- 2311.06668 In-context Vectors: Making In Context Learning More Effective and Cont
        23801, -- 2311.15766 Knowledge Unlearning for LLMs: Tasks, Methods, and Challenges
        24427, -- 2312.04339 Merging by Matching Models in Task Parameter Subspaces
        24641, -- 2312.06795 Model Breadcrumbs: Scaling Multi-Task Model Merging with Sparse Masks
        24977, -- 2312.12148 Parameter-Efficient Fine-Tuning Methods for Pretrained Language Models
        25123, -- 2312.14378 Multimodal Attention Merging for Improved Speech Recognition and Audio
        25408, -- 2401.01286 A Comprehensive Study of Knowledge Editing for Large Language Models
        25456, -- 2401.01967 A Mechanistic Understanding of Alignment Algorithms: A Case Study on D
        25492, -- 2401.02412 LLM Augmented LLMs: Expanding Capabilities through Composition
        26141, -- 2401.12187 WARM: On the Benefits of Weight Averaged Reward Models
        26510, -- 2401.17514 How Useful is Continued Pre-Training for Generative Unsupervised Domai
        26750, -- 2402.02263 MixedNUTS: Training-Free Accuracy-Robustness Balance via Nonlinearly M
        26788, -- 2402.02705 Representation Surgery for Multi-Task Model Merging
        27069, -- 2402.05859 Learning to Route Among Specialized Experts for Zero-Shot Generalizati
        27086, -- 2402.05966 Vanishing Feature: Diagnosing Model Merging and Beyond
        27287, -- 2402.08787 Rethinking Machine Unlearning for Large Language Models
        27621, -- 2402.12550 Multilinear Mixture of Experts: Scalable Expert Specialization through
        27822, -- 2402.14688 Q-Probe: A Lightweight Approach to Reward Maximization for Language Mo
        27843, -- 2402.14811 Fine-Tuning Enhances Existing Mechanisms: A Case Study on Entity Track
        27951, -- 2402.16107 Knowledge Fusion of Chat LLMs: A Preliminary Technical Report
        27953, -- 2402.16123 InstructEdit: Instruction-based Knowledge Editing for Large Language M
        27999, -- 2402.16828 Training Neural Networks from Scratch with Parallel Low-Rank Adapters
        28002, -- 2402.16835 Eight Methods to Evaluate Robust Unlearning in LLMs
        28101, -- 2402.17934 Inducing Generalization across Languages and Tasks using Featurized Lo
        28446, -- 2403.03218 The WMDP Benchmark: Measuring and Reducing Malicious Use With Unlearni
        28683, -- 2403.06952 SELMA: Learning and Merging Skill-Specific Text-to-Image Experts with
        29071, -- 2403.12035 CoCoCo: Improving Text-Guided Video Inpainting for Better Consistency,
        29160, -- 2403.13187 Evolutionary Optimization of Model Merging Recipes
        29385, -- 2403.16024 A Unified Module for Accelerating STABLE-DIFFUSION: LCM-LORA
        29616, -- 2403.19522 Model Stock: All we need is just a few fine-tuned models
        29864, -- 2404.02241 Linear Combination of Saved Checkpoints Makes Consistency and Diffusio
        30262, -- 2404.08079 DIMAT: Decentralized Iterative Merging-And-Training for Deep Learning
        30367, -- 2404.09656 Learn Your Reference Model for Real Good Alignment
        30386, -- 2404.09977 MaxFusion: Plug&Play Multi-Modal Generation in Text-to-Image Diffusion
        30460, -- 2404.11225 In-Context Learning State Vector with Inner and Momentum Optimization
        30473, -- 2404.11534 Decomposing and Editing Predictions by Modeling Model Computation
        30881, -- 2404.18466 HFT: Half Fine-Tuning for Large Language Models
        31013, -- 2405.01453 Creative Problem Solving in Large Language and Vision Models -- What W
        31219, -- 2405.07288 Erasing Concepts from Text-to-Image Diffusion Models with Few-shot Unl
        31253, -- 2405.07883 Zero-Shot Tokenizer Transfer
        31400, -- 2405.11157 Towards Modular LLMs by Building and Reusing a Library of LoRAs
        31495, -- 2405.13053 MeteoRA: Multiple-tasks Embedded LoRA for Large Language Models
        31547, -- 2405.13967 Model Editing as a Robust and Denoised variant of DPO: A Case Study on
        31600, -- 2405.14596 Linear Mode Connectivity in Differentiable Tree Ensembles
        31617, -- 2405.14768 WISE: Rethinking the Knowledge Memory for Lifelong Model Editing of La
        31823, -- 2405.17082 Ensembling Diffusion Models via Adaptive Feature Aggregation
        31908, -- 2405.18069 An Empirical Analysis of Forgetting in Pre-trained Models with Increme
        32056, -- 2405.19950 Multimodal Lego: Model Merging and Fine-Tuning Across Topologies and M
        32331, -- 2406.02699 Operational Latent Spaces
        32448, -- 2406.04313 Improving Alignment and Robustness with Circuit Breakers
        32732, -- 2406.07529 MAP: Low-compute Model Merging with Amortized Pareto Fronts via Quadra
        32903, -- 2406.09413 Interpreting the Weight Space of Customized Diffusion Models
        33032, -- 2406.10890 RWKU: Benchmarking Real-World Knowledge Unlearning for Large Language
        33070, -- 2406.11194 In-Context Editing: Learning Knowledge from Self-Induced Distributions
        33194, -- 2406.12034 Self-MoE: Towards Compositional Large Language Models with Self-Specia
        33441, -- 2406.14764 RE-AdaptIR: Improving Information Retrieval through Reverse Engineered
        33493, -- 2406.15479 Twin-Merging: Dynamic Integration of Modular Expertise in Model Mergin
        33567, -- 2406.16330 Pruning via Merging: Compressing LLMs via Manifold Alignment Based Lay
        33597, -- 2406.16768 WARP: On the Benefits of Weight Averaged Rewarded Policies
        33694, -- 2406.17923 PAFT: A Parallel Training Paradigm for Effective LLM Fine-Tuning
        33759, -- 2406.18664 Evaluating Copyright Takedown Methods for Language Models
        34053, -- 2407.02447 PLeaS -- Merging Models with Permutations and Least Squares
        34343, -- 2407.06322 MagMax: Leveraging Model Merging for Seamless Continual Learning
        34456, -- 2407.08056 Pareto Low-Rank Adapters: Efficient Multi-Task Learning with Preferenc
        34767, -- 2407.11867 Unlearning Targeted Information via Single Layer Unlearning Gradient
        35004, -- 2407.14962 Recent Advances in Generative AI and Large Language Models: Current St
        35174, -- 2407.17571 Diffusion Models For Multi-Modal Generative Modeling
        35569, -- 2408.02718 MMIU: Multimodal Multi-image Understanding for Evaluating Large Vision
        35588, -- 2408.03092 Extend Model Merging from Fine-Tuned to Pre-Trained Large Language Mod
        35776, -- 2408.06621 Towards Robust and Parameter-Efficient Knowledge Unlearning for LLMs
        35811, -- 2408.07057 A Survey on Model MoErging: Recycling and Routing Among Specialized Ex
        35844, -- 2408.07666 Model Merging in LLMs, MLLMs, and Beyond: Methods, Theories, Applicati
        35854, -- 2408.07990 FuseChat: Knowledge Fusion of Chat Models
        35946, -- 2408.09503 Out-of-distribution generalization via composition: a lens through ind
        36333, -- 2408.15915 Leveraging Open Knowledge for Advancing Task Expertise in Large Langua
        36553, -- 2409.02228 Unforgettable Generalization in Language Models
        37279, -- 2409.16167 Merging LoRAs like Playing LEGO: Pushing the Modularity of LoRA to Ext
        37412, -- 2409.18314 Realistic Evaluation of Model Merging for Compositional Generalization
        37515, -- 2409.19886 RouterDC: Query-Based Router by Dual Contrastive Learning for Assembli
        37637, -- 2410.01335 Layer Swapping for Zero-Shot Cross-Lingual Transfer in Large Language
        37669, -- 2410.01610 Upcycling Instruction Tuning from Dense to Mixture-of-Experts via Para
        37756, -- 2410.02396 Parameter Competition Balancing for Model Merging
        37885, -- 2410.03617 What Matters for Model Merging at Scale?
        37906, -- 2410.03782 DaWin: Training-free Dynamic Weight Interpolation for Robust Adaptatio
        37984, -- 2410.04891 Low-Rank Continual Personalization of Diffusion Models
        38054, -- 2410.05603 Everything Everywhere All at Once: LLMs can In-Context Learn Multiple
        38091, -- 2410.06084 Diversity-Rewarded CFG Distillation
        38143, -- 2410.06664 Decouple-Then-Merge: Towards Better Training for Diffusion Models
        38187, -- 2410.07163 Simplicity Prevails: Rethinking Negative Preference Optimization for L
        38194, -- 2410.07172 Glider: Global and Local Instruction-Driven Expert Router
        38218, -- 2410.07571 How Does Vision-Language Adaptation Impact the Safety of Vision Langua
        38350, -- 2410.09344 DARE the Extreme: Revisiting Delta-Parameter Pruning For Fine-Tuned Mo
        38465, -- 2410.10801 Mix Data or Merge Models? Optimizing for Diverse Multi-Task Learning
        38508, -- 2410.11143 LLM Unlearning via Loss Adjustment with Only Forget Data
        38618, -- 2410.12613 Exploring Model Kinship for Merging Large Language Models
        38753, -- 2410.13841 A Unified View of Delta Parameter Editing in Post-Trained Large-Scale
        38765, -- 2410.13910 Mitigating the Backdoor Effect for Multi-Task Model Merging via Safety
        38833, -- 2410.14735 Agent Skill Acquisition for Large Language Models via CycleQD
        38843, -- 2410.14940 Baichuan Alignment Technical Report
        38996, -- 2410.17050 UnStar: Unlearning with Self-Taught Anti-Sample Reasoning for LLMs
        39002, -- 2410.17146 LiNeS: Post-training Layer Scaling Prevents Forgetting and Enhances Mo
        39482, -- 2411.00204 RESTOR: Knowledge Recovery through Machine Unlearning
        39754, -- 2411.04986 The Semantic Hub Hypothesis: Language Models Share Semantic Representa
        39782, -- 2411.05239 ZipNN: Lossless Compression for AI Models
        39998, -- 2411.09249 Enhancing Financial Domain Adaptation of Language Models via Model Aug
        40102, -- 2411.11296 Steering Language Model Refusal with Sparse Autoencoders
        40288, -- 2411.14725 Evaluating and Advancing Multimodal Large Language Models in Ability L
        41139, -- 2412.05148 LoRA.rar: Learning to Merge LoRAs via Hypernetworks for Subject-Style
        41554, -- 2412.10416 SUPERMERGE: An Approach For Gradient-Based Model Merging
        41561, -- 2412.10493 SafetyDPO: Scalable Safety Alignment for Text-to-Image Generation
        41692, -- 2412.12048 A LoRA is Worth a Thousand Pictures
        42208, -- 2412.19098 Tint Your Models Task-wise for Improved Multi-task Model Merging
        42245, -- 2412.19726 Can Large Language Models Adapt to Other Agents In-Context?
        42315, -- 2412.21140 Facilitating large language model Russian adaptation with Learned Embe
        42511, -- 2501.02795 InfiFusion: A Unified Framework for Enhanced Cross-Model Reasoning via
        42698, -- 2501.05767 Migician: Revealing the Magic of Free-Form Multi-Image Grounding in Mu
        43546, -- 2502.01083 Tool Unlearning for Tool-Augmented LLMs
        43651, -- 2502.02421 Activation-Informed Merging of Large Language Models
        43832, -- 2502.04959 No Task Left Behind: Isotropic Model Merging with Common and Task-Spec
        44004, -- 2502.07218 LUNAR: LLM Unlearning via Neural Activation Redirection
        44051, -- 2502.07760 Scalable Fingerprinting of Large Language Models
        44220, -- 2502.10436 MERGE$^3$: Efficient Evolutionary Merging on Consumer-grade GPUs
        44229, -- 2502.10525 Towards Watermarking of Open-Source LLMs
        44763, -- 2502.15483 MoMa: A Modular Deep Learning Framework for Material Property Predicti
        44882, -- 2502.16894 Make LoRA Great Again: Boosting LoRA with Adaptive Singular Values and
        44915, -- 2502.17159 Parameter Efficient Merging for Multimodal Large Language Models with
        45289, -- 2503.00948 Extrapolating and Decoupling Image-to-Video Generation Models: Motion
        46211, -- 2503.12649 FW-Merging: Scaling Model Merging with Frank-Wolfe Optimization
        46766, -- 2503.20110 Efficient Model Development through Fine-tuning Transfer
        46839, -- 2503.21272 Reinforced Model Merging
        47032, -- 2503.23733 AdaMMS: Model Merging for Heterogeneous Multimodal Large Language Mode
        47142, -- 2504.01196 $μ$KE: Matryoshka Unstructured Knowledge Editing of Large Language Mod
        47408, -- 2504.05747 SEA-LION: Southeast Asian Languages in One Network
        47485, -- 2504.07448 LoRI: Reducing Cross-Task Interference in Multi-Task Low-Rank Adaptati
        47809, -- 2504.12364 DMM: Building a Versatile Image Generation Model via Distillation-Base
        48148, -- 2504.18580 Parameter-Efficient Checkpoint Merging via Metrics-Weighted Averaging
        48339, -- 2505.01456 Unlearning Sensitive Information in Multimodal LLMs: Benchmark and Att
        48524, -- 2505.05064 WaterDrum: Watermarking for Data-centric Unlearning Metric
        48539, -- 2505.05464 Bring Reason to Vision: Understanding Perception and Reasoning through
        48797, -- 2505.10717 A Modular Approach for Clinical SLMs Driven by Synthetic Data with Pre
        48924, -- 2505.12082 Model Merging in Pre-training of Large Language Models
        48990, -- 2505.12716 Shadow-FT: Tuning Instruct via Base
        49050, -- 2505.13312 GUARD: Generation-time LLM Unlearning via Adaptive Restriction and Det
        49137, -- 2505.14185 Safety Subspaces are Not Distinct: A Fine-Tuning Case Study
        49187, -- 2505.14513 Latent Flow Transformer
        49213, -- 2505.14667 SAFEPATH: Preventing Harmful Reasoning in Chain-of-Thought via Early A
        49235, -- 2505.14827 Text Generation Beyond Discrete Token Sampling
        49370, -- 2505.16151 Training-Free Reasoning and Reflection in MLLMs
        49619, -- 2505.18502 Knowledge Grafting of Large Language Models
        49679, -- 2505.19075 Universal Reasoner: A Single, Composable Plug-and-Play Reasoner for Fr
        50913, -- 2506.09227 SoK: Machine Unlearning for Large Language Models
        51462, -- 2506.20480 GPTailor: Large Language Model Pruning Through Layer Cutting and Stitc
        51797, -- 2507.07024 FlexOlmo: Open Language Models for Flexible Data Use
        52382, -- 2508.11032 MedSAMix: A Training-Free Model Merging Approach for Medical Image Seg
        52658, -- 2509.04442 Delta Activations: A Representation for Finetuned Large Language Model
        52916, -- 2509.17786 Accurate and Efficient Low-Rank Model Merging in Core Space
        53106, -- 2510.00232 BiasFreeBench: a Benchmark for Mitigating Bias in Large Language Model
        53271, -- 2510.06052 MixReasoning: Switching Modes to Think
        53285, -- 2510.06036 Refusal Falls off a Cliff: How Safety Alignment Fails in Reasoning?
        53760, -- 2510.15050 Directional Reasoning Injection for Fine-Tuning MLLMs
        54216, -- 2511.13254 Souper-Model: How Simple Arithmetic Unlocks State-of-the-Art LLM Perfo
        54916, -- 2512.15586 Bolmo: Byteifying the Next Generation of Language Models
        54988, -- 2512.13043 GTR-Turbo: Merged Checkpoint is Secretly a Free Teacher for Agentic VL
        55159, -- 2601.05106 Token-Level LLM Collaboration via FusionRoute
        55391, -- 2601.14004 Locate, Steer, and Improve: A Practical Survey of Actionable Mechanist
        55399, -- 2601.14251 LightOnOCR: A 1B End-to-End Multilingual Vision-Language Model for Sta
        55730, -- 2602.00747 Decouple Searching from Training: Scaling Data Mixing via Model Mergin
        55894, -- 2602.06964 Learning a Generative Meta-Model of LLM Activations
        55969, -- 2602.07276 Steer2Adapt: Dynamically Composing Steering Vectors Elicits Efficient
        56057, -- 2602.09021 χ_{0}: Resource-Aware Robust Manipulation via Taming Distributional In
        56081, -- 2602.11543 Pretraining A Large Language Model using Distributed GPUs: A Memory-Ef
        56505, -- 2603.03942 Lightweight Visual Reasoning for Socially-Aware Robots
        56567, -- 2603.07236 HY-WU (Part I): An Extensible Functional Neural Memory Framework and A
        56783, -- 2603.13875 GradMem: Learning to Write Context into Memory with Test-Time Gradient
        57064, -- 2603.27027 TAPS: Task Aware Proposal Distributions for Speculative Sampling
        57112, -- 2604.00007 Dynin-Omni: Omnimodal Unified Large Diffusion Language Model
        57193, -- 2604.00829 LinguDistill: Recovering Linguistic Ability in Vision- Language Models
        57263, -- 2604.02045 BidirLM: From Text to Omnimodal Bidirectional Encoders by Adapting and
        57357, -- 2604.06377 The Master Key Hypothesis: Unlocking Cross-Model Capability Transfer v
        57380, -- 2604.02372 Backdoor Attacks on Decentralised Post-Training
        57386, -- 2604.09544 Large Language Models Generate Harmful Content Using a Distinct, Unifi
        57415, -- 2604.05336 TRACE: Capability-Targeted Agentic Training
        57561, -- 2604.05716 Can Large Language Models Reinvent Foundational Algorithms?
        57891, -- 2512.09972 AP-BMM: Approximating Capability-Efficiency Pareto Sets of LLMs via As
        58696, -- 2603.29765 Training-Free Dynamic Upcycling of Expert Language Models
        58710, -- 2604.02371 Internalized Reasoning for Long-Context Visual Document Understanding
        58783, -- 2603.12681 Colluding LoRA: A Compositional Vulnerability in LLM Safety Alignment
        59823, -- 2603.05813 Activation Steering for Accent Adaptation in Speech Foundation Models
        59860, -- 2603.04964 Replaying pre-training data improves fine-tuning
        59904, -- 2603.03995 Spectral Surgery: Training-Free Refinement of LoRA via Gradient-Guided
        60521, -- 2602.16698 Causality is Key for Interpretability Claims to Generalise
        60591, -- 2602.15257 How to Train Your Long-Context Visual Document Model
        60731, -- 2602.12566 To Mix or To Merge: Toward Multi-Domain Reinforcement Learning for Lar
        60745, -- 2602.12323 The Appeal and Reality of Recycling LoRAs with Adaptive Merging
        60829, -- 2602.10993 LoRA-Squeeze: Simple and Effective Post-Tuning and In-Tuning Compressi
        61085, -- 2602.06623 Do Prompts Guarantee Safety? Mitigating Toxicity from LLM Generations
        61104, -- 2602.17692 Agentic Unlearning: When LLM Agent Meets Machine Unlearning
        61127, -- 2602.06248 REBEL: Hidden Knowledge Recovery via Evolutionary-Based Evaluation Loo
        61169, -- 2602.05495 Transport and Merge: Cross-Architecture Merging for Large Language Mod
        61197, -- 2602.05943 Orthogonal Model Merging
        61236, -- 2602.04937 Linear Model Merging Unlocks Simple and Scalable Multimodal Data Mixtu
        61245, -- 2602.04521 C-ΔΘ: Circuit-Restricted Weight Arithmetic for Selective Refusal
        61249, -- 2602.04447 Mixture of Masters: Sparse Chess Language Models with Player Routing
        61320, -- 2602.03696 Conflict-Resolving and Sharpness-Aware Minimization for Generalized Kn
        62070, -- 2601.17858 MergeMix: Optimizing Mid-Training Data Mixtures via Learnable Model Me
        62312, -- 2601.13580 Neural Organ Transplantation (NOT): Checkpoint-Based Modular Adaptatio
        62658, -- 2601.07309 ARM: Role-Conditioned Neuron Transplantation for Training-Free General
        63109, -- 2601.00590 SafeMo: Linguistically Grounded Unlearning for Trustworthy Text-to-Mot
        64096, -- 2512.05117 The Universal Weight Subspace Hypothesis
        64633, -- 2511.18810 MergeVLA: Cross-Skill Model Merging Toward a Generalist Vision-Languag
        65587, -- 2510.27265 T3: Test-Time Model Merging in VLMs for Zero-Shot Medical Imaging Anal
        66155, -- 2510.17598 Reasoning Distillation and Structural Alignment for Improved Code Gene
        66346, -- 2510.14163 Towards Reversible Model Merging For Low-rank Weights
        66351, -- 2510.13999 REAP the Experts: Why Pruning Prevails for One-Shot MoE compression
        66711, -- 2510.08396 FlyLoRA: Boosting Task Decoupling and Parameter Efficiency via Implici
        66919, -- 2510.05092 Learning to Interpret Weight Differences in Language Models
        66920, -- 2510.05064 Boomerang Distillation Enables Zero-Shot Model Size Interpolation
        67702, -- 2509.22158 Context Parametrization with Compositional Adapters
        67836, -- 2509.20758 SFT Doesn't Always Hurt General Capabilities: Revisiting Domain-Specif
        68408, -- 2509.11414 Continually Adding New Languages to Multilingual Language Models
        68424, -- 2509.11167 Harnessing Optimization Dynamics for Curvature-Informed Model Merging
        68799, -- 2509.02820 Unlearning That Lasts: Utility-Preserving, Robust, and Almost Irrevers
        68866, -- 2509.01548 Model Unmerging: Making Your Models Unmergeable for Secure Model Shari
        69131, -- 2508.19353 Efficient Multi-Source Knowledge Transfer by Model Merging
        69309, -- 2508.16463 Modular Embedding Recomposition for Incremental Learning
        69360, -- 2508.15507 Think in Blocks: Adaptive Reasoning from Direct Response to Deep Reaso
        69559, -- 2508.12491 Cost-Aware Contrastive Routing for LLMs
        70071, -- 2508.05059 Learning from Oblivion: Predicting Knowledge Overflowed Weights via Re
        70226, -- 2508.03121 RegMean++: Enhancing Effectiveness and Generalization of Regression Me
        70640, -- 2507.20718 Uncertainty-driven Embedding Convolution
        70909, -- 2507.16003 Learning without training: The implicit dynamics of in-context learnin
        71634, -- 2506.23423 TuCo: Measuring the Contribution of Fine-Tuning to Individual Response
        71763, -- 2506.19140 Command-V: Pasting LLM Behaviors via Activation Profiles
        71961, -- 2506.13234 The Butterfly Effect: Neural Network Training Trajectories Are Highly
        72013, -- 2506.11613 Model Organisms for Emergent Misalignment
        72472, -- 2506.14794 Assembly of Experts: Linear-time construction of the Chimera LLM varia
        72556, -- 2505.23117 Decom-Renorm-Merge: Model Merging on the Right Space Improves Multitas
        72568, -- 2505.22635 Learning Composable Chains-of-Thought
        72783, -- 2505.18102 How Can I Publish My LLM Benchmark Without Giving the True Answers Awa
        72881, -- 2505.15875 Decouple and Orthogonalize: A Data-Free Framework for LoRA Merging
        72937, -- 2505.14136 Local Mixtures of Experts: Essentially Free Test-Time Training via Mod
        73004, -- 2505.11998 Parameter Efficient Continual Learning with Dynamic Low-Rank Adaptatio
        73051, -- 2505.10833 MergeBench: A Benchmark for Merging Domain-Specialized LLMs
        73527, -- 2504.09757 Alleviating the Fear of Losing Alignment in LLM Fine-tuning
        73944, -- 2410.16454 Catastrophic Failure of LLM Unlearning via Quantization
        74614, -- 2502.12776 Portable Reward Tuning: Towards Reusable Fine-Tuning across Different
        74830, -- 2502.05390 Learning Task Representations from In-Context Learning
        75666, -- 2411.19154 DESIRE: Dynamic Knowledge Consolidation for Rehearsal-Free Continual L
        75893, -- 2411.00553 Is Multiple Object Tracking a Matter of Specialization?
        76017, -- 2410.13569 Learning on Model Weights using Tree Experts
        76031, -- 2410.13025 LoRA Soups: Merging LoRAs for Practical Skill Composition Tasks
        76047, -- 2410.11536 OVS Meets Continual Learning: Towards Sustainable Open-Vocabulary Segm
        76075, -- 2410.09508 CollabEdit: Towards Non-destructive Collaborative Knowledge Editing
        76121, -- 2410.06467 WAPITI: A Watermark for Finetuned Open-Source LLMs
        76267, -- 2405.17461 EMR-Merging: Tuning-Free High-Performance Model Merging
        76865, -- 2407.00487 It's Morphing Time: Unleashing the Potential of Multiple LLMs via Mult
        77178, -- 2405.17374 Navigating the Safety Landscape: Measuring Risks in Finetuning Large L
        77195, -- 2405.16350 A Second-Order Perspective on Model Compositionality and Incremental L
        82896, -- 2605.06477 GeoStack: A Framework for Quasi-Abelian Knowledge Composition in VLMs
        82972, -- 2509.24244 Model Merging Scaling Laws in Large Language Models
        83169, -- 2605.14386 Darwin Family: MRI-Trust-Weighted Evolutionary Merging for Training-Fr
        83507, -- 2605.21468 You Only Need Minimal RLVR Training: Extrapolating LLMs via Rank-1 Tra
        84161, -- 2511.11851 Defending Unauthorized Model Merging via Dual-Stage Weight Protection
        84572, -- 2602.20208 Model Merging in the Essential Subspace
        84721, -- 2603.02945 ACE-Merging: Data-Free Model Merging with Adaptive Covariance Estimati
        84737, -- 2603.03920 BD-Merging: Bias-Aware Dynamic Model Merging with Evidence-Guided Cont
        84767, -- 2603.05768 Bridging Domains through Subspace-Aware Model Merging
        84875, -- 2603.12433 Revisiting Model Stitching In the Foundation Model Era
        85147, -- 2603.26299 Preference-Aligned LoRA Merging: Preserving Subspace Coverage and Addr
        85148, -- 2603.26317 Label-Free Cross-Task LoRA Merging with Null-Space Compression
        85285, -- 2604.05183 OrthoFuse: Training-free Riemannian Fusion of Orthogonal Style-Concept
        85773, -- 2505.11883 MINGLE: Mixtures of Null-Space Gated Low-Rank Experts for Test-Time Co
        85896, -- 2505.14009 Activation-Guided Consensus Merging for Large Language Models
        86332, -- 2502.01472 FALCON: Fine-grained Activation Manipulation by Contrastive Orthogonal
        86350, -- 2506.06609 Transferring Features Across Language Models With Model Stitching
        86448, -- 2506.05735 Do LLMs Really Forget? Evaluating Unlearning with Knowledge Correlatio
        86493, -- 2510.14387 Can MLLMs Absorb Math Reasoning Abilities from LLMs as Free Lunch?
        86654, -- 2505.16524 CodeMerge: Codebook-Guided Model Merging for Robust Test-Time Adaptati
        86909, -- 2410.01508 Disentangling Latent Shifts of In-Context Learning with Weak Supervisi
        87172, -- 2503.09271 DitHub: A Modular Framework for Incremental Open-Vocabulary Object Det
        87247, -- 2409.18893 HM3: Hierarchical Multi-Objective Model Merging for Pretrained Models
        87272, -- 2505.18651 On the Emergence of Linear Analogies in Word Embeddings
        87343, -- 2505.17013 When Are Concepts Erased From Diffusion Models?
        87380, -- 2505.12075 Do different prompting methods yield a common task representation in l
        87728, -- 2503.07661 Disrupting Model Merging: A Parameter-Level Defense Without Sacrificin
        88016, -- 2507.04790 Interaction-Merged Motion Planning: Effectively Leveraging Diverse Mot
        88801, -- 2412.08559 Underestimated Privacy Risks for Minority Populations in Large Languag
        88947, -- 2505.19313 Concept Reachability in Diffusion Models: Beyond Dataset Constraints
        89233, -- 2406.13348 Textual Unlearning Gives a False Sense of Unlearning
        89257, -- 2410.11163 Model Swarms: Collaborative Search to Adapt LLM Experts via Swarm Inte
        89694, -- 2502.12706 Scalable Model Merging with Progressive Layer-wise Distillation
        89848, -- 2502.04549 Mechanisms of Projective Composition of Diffusion Models
        89908, -- 2505.11953 Exploring Criteria of Loss Reweighting to Enhance LLM Unlearning
        89909, -- 2503.09117 GRU: Mitigating the Trade-off between Unlearning and Retention for LLM
        89964, -- 2504.02666 BECAME: Bayesian Continual Learning with Adaptive Model Merging
        89990, -- 2502.02797 Upweighting Easy Samples in Fine-Tuning Mitigates Forgetting
        90149, -- 2503.15842 FedAWA: Adaptive Optimization of Aggregation Weights in Federated Lear
        90157, -- 2505.06068 Noise-Consistent Siamese-Diffusion for Medical Image Synthesis and Seg
        90256, -- 2410.00911 Dual Consolidation for Pre-Trained Model-Based Domain-Incremental Lear
        90506, -- 2409.16434 Lessons and Insights from a Unifying Study of Parameter-Efficient Fine
        90711, -- 2412.18219 Adapter Merging with Centroid Prototype Mapping for Scalable Class-Inc
        90725, -- 2210.13533 Sufficient Invariant Learning for Distribution Shift
        90727, -- 2411.15231 IterIS: Iterative Inference-Solving Alignment for LoRA Merging
        90817, -- 2503.18985 LoRA Subtraction for Drift-Resistant Space in Exemplar-Free Continual
        90950, -- 2412.06712 How to Merge Your Multimodal Models Over Time?
        91125, -- 2410.19735 Model merging with SVD to tie the Knots
        91381, -- 2410.09343 ELICIT: LLM Augmentation Via External In-context Capability
        91544, -- 2410.12877 Improving Instruction-Following in Language Models through Activation
        91576, -- 2410.17961 Closed-Form Merging of Parameter-Efficient Modules for Federated Conti
        91664, -- 2502.18821 CAMEx: Curvature-aware Merging of Experts
        91973, -- 2410.09591 Unlearn and Burn: Adversarial Machine Unlearning Requests Destroy Mode
        92010, -- 2410.00700 Mining your own secrets: Diffusion Classifier Scores for Continual Per
        92137, -- 2406.09179 Towards Effective Evaluations and Comparisons for LLM Unlearning Metho
        92472, -- 2606.01717 Decentralized Instruction Tuning: Conflict-Aware Splitting and Weight
        92561, -- 2606.05165 STRIDE: Training Data Attribution via Sparse Recovery from Subset Pert
        92644, -- 2511.05408 Steering Language Models with Weight Arithmetic
        92735, -- 2506.20941 Revisiting the Past: Data Unlearning with Model State History
        92745, -- 2512.23017 Merge before Forget: A Single LoRA Continual Learning via Continual Me
        92841, -- 2504.05342 MASS: MoErging through Adaptive Subspace Selection
        93367, -- 2603.09888 LCA: Local Classifier Alignment for Continual Learning
        93399, -- 2506.03674 Out-of-Distribution Graph Models Merging
        93420, -- 2603.01526 Scalable Multi-Task Low-Rank Model Adaptation
        93427, -- 2604.10636 Mitigating Privacy Risk via Forget Set-Free Unlearning
        93430, -- 2505.23209 Navigating the Accuracy-Size Trade-Off with Flexible Model Merging
        93487, -- 2508.00161 Watch the Weights: Unsupervised monitoring and control of fine-tuned L
        93520, -- 2601.21283 DUET: Distilled LLM Unlearning from an Efficiently Contextualized Teac
        93607, -- 2506.14003 Unlearning Isn't Invisible: Detecting Unlearning Traces in LLMs from M
        93700, -- 2509.23487 Temporal Generalization: A Reality Check
        93719, -- 2511.05784 DRAGON: Guard LLM Unlearning in Context via Negative Detection and Rea
        93868, -- 2506.16975 Latent Concept Disentanglement in Transformer-based Language Models
        93904, -- 2506.20746 Dynamic Weight Grafting: Localizing Finetuned Factual Knowledge in Tra
        93932, -- 2503.10705 Enhanced Continual Learning of Vision-Language Models with Model Fusio
        93976, -- 2509.23362 Dual-Space Smoothness for Robust and Balanced LLM Unlearning
        94002, -- 2602.00782 Controlling Repetition in Protein Language Models
        94195, -- 2603.01285 Attention Smoothing Is All You Need For Unlearning
        94277, -- 2505.20925 Multi-objective Large Language Model Alignment with Hierarchical Exper
        94286, -- 2502.07274 Forget Forgetting: Continual Learning in a World of Abundant Memory
        94483, -- 2506.15076 Learning-Time Encoding Shapes Unlearning in LLMs
        94561, -- 2511.07970 Continual Unlearning for Text-to-Image Diffusion Models: A Regularizat
        94620, -- 2604.06285 Harnessing Hyperbolic Geometry for Harmful Prompt Detection and Saniti
        94791, -- 2601.10497 MergeTune: Continued Fine-Tuning of Vision-Language Models
        95096, -- 2606.05846 Towards Truly Multilingual ASR: Generalizing Code-Switching ASR to Uns
        98323, -- 2606.13657 Dense Supervision, Sparse Updates: On the Sparsity and Geometry of On-
        98846, -- 2606.27377 DanceOPD: On-Policy Generative Field Distillation
        98887, -- 2606.26080 Neglected Free Lunch from Post-training: Progress Advantage for LLM Ag
        98985, -- 2606.28525 A Gravitational Interpretation of Fine-Tuning Reversion
        99039, -- 2607.00666 Domain Arithmetic: One-Shot VLA Adaptation under Environmental Shifts
        99078, -- 2607.02291 Optimizing Visual Generative Models via Distribution-wise Rewards
        99099, -- 2607.01686 WARP: Weight-Space Analysis for Recovering Training Data Portfolios
        99314, -- 2605.29295 EvoGM: Learning to Merge LLMs via Evolutionary Generative Optimization
        99489, -- 2603.00191 Task-Driven Subspace Decomposition for Knowledge Sharing and Isolation
        99606, -- 2605.14289 MetaMoE: Diversity-Aware Proxy Selection for Privacy-Preserving Mixtur
        99679, -- 2605.16704 Convex Dataset Valuation for Post-Training
        99706, -- 2512.00902 Don't Reinvent the Wheel, Just Realign the Spokes: Resource-Efficient
        99736, -- 2606.10617 SSR-Merge: Subspace Signal Routing for Training-Free LoRA Merging in D
        99820, -- 2605.26484 Extra-Merge: Tracing the Rank-1 Subspace of Model Merging in Language
        99824, -- 2606.25761 Bridging Spherical Black-Box Optimizers
        100165, -- 2605.05995 Safety Anchor: Defending Harmful Fine-tuning via Geometric Bottlenecks
        100230, -- 2601.22285 Demystifying Mergeability: Interpretable Properties to Predict Model M
        100331, -- 2605.24550 Jailbreak to Protect: Buffering and Reinforcing via Temporary Jailbrea
        100345, -- 2602.00722 Spectral Imbalance Causes Forgetting in Low-Rank Continual Adaptation
        100563, -- 2602.17554 A Theoretical Framework for Modular Learning of Robust Generative Mode
        100578, -- 2605.15207 TeamTR: Trust-Region Fine-Tuning for Multi-Agent LLM Coordination
        100636, -- 2605.19409 Unlocking the Potential of Continual Model Merging: An ODE Perspective
        100738, -- 2605.22350 Partial Fusion of Neural Networks: Efficient Tradeoffs Between Ensembl
        100755, -- 2606.16501 Post-Hoc Merging is Not Enough: Many-Shot Model Merging with Loss-Gap
        100778, -- 2606.14997 AI Engram: In Search of Memory Traces in Artificial Intelligence
        100831, -- 2606.03723 Compress then Merge: From Multiple LoRAs into One Low-Rank Adapter
        100885, -- 2603.03326 Controllable and Explainable Personality Sliders for LLMs at Inference
        100917, -- 2605.04572 From Parameter Dynamics to Risk Scoring: Quantifying Sample-Level Safe
        101008, -- 2509.16447 Local Mechanisms of Compositional Generalization in Conditional Diffus
        101297, -- 2509.23782 Bridging the Knowledge-Prediction Gap in LLMs on Multiple-Choice Quest
        101372, -- 2602.00533 Convergent World Representations and Divergent Tasks
        101546, -- 2601.21898 Making Models Unmergeable via Scaling-Sensitive Loss Landscape
        101653, -- 2606.03232 GFFMERGE: Efficient Merging of Graph Neural Force Fields and Beyond
        101940, -- 2602.23164 MetaOthello: A Controlled Study of Multiple World Models in Transforme
        101985, -- 2506.14126 From Memorization to Parameter Interference: How Overtraining Experts
        102091, -- 2605.30132 Learning to Extrapolate to New Tasks: A Relational Approach to Task Ex
        102230, -- 2510.22491 LAMP: Data-Efficient Linear Affine Weight-Space Models for Parameter-C
        102281, -- 2605.31293 Divergence Decoding: Inference-Time Unlearning via Auxiliary Models
        102346, -- 2602.09689 MODEL SOUPS NEED ONLY ONE INGREDIENT
        102785, -- 2502.19982 Erasing Without Remembering: Implicit Knowledge Forgetting in Large La
        103426, -- 2410.02684 HiddenGuard: Fine-Grained Safe Generation with Specialized Representat
        103714, -- 2505.21226 Why Do More Experts Fail? A Theoretical Analysis of Model Merging
        103864, -- 2607.05394 Weak-to-Strong Generalization via Direct On-Policy Distillation
        104051, -- 2607.03065 Spectral Rewiring for Exploration, Purification, and Model Merging
        104452, -- 2607.19331 ISO: An RLVR-Native Optimization Stack
        104536, -- 2605.20296 Spectral Unforgetting: Post-Hoc Recovery of Damaged Capabilities Witho
        104560, -- 2607.05471 KAT-Coder-V2.5 Technical Report
        105401, -- 2503.01164 Med-LEGO: Editing and Adapting toward Generalist Medical Image Diagnos
        105646, -- 2503.07799 Self-supervised Normality Learning and Divergence Vector-guided Model
        106098, -- 2604.04231 Subspace Control: Turning Constrained Model Steering into Controllable
        106250, -- 2601.16905 GRIP: Algorithm-Agnostic Machine Unlearning for Mixture-of-Experts via
        106255, -- 2604.01329 Model Merging via Data-Free Covariance Estimation
        106291, -- 2606.30044 Building Multi-Task Agentic LLMs via Two-Phase Distillation
        106321, -- 2604.06465 Multi-objective Evolutionary Merging Enables Efficient Reasoning Model
        106342, -- 2510.17021 Forgetting to Forget: Attention Sink as A Gateway for Backdooring LLM
        108374, -- 2504.06768 FedMerge: Federated Model Merging for Personalization
        108781, -- 2605.10903 CapVector: Learning Transferable Capability Vectors in Parametric Spac
        108939, -- 2608.06216 Continual Learning in Transition
        108974, -- 2608.03573 SFT Conflicts, RL Coexists: A Theoretical and Empirical Analysis of Mu
        108983, -- 2608.06756 Capek 0.5: An Execution-Centric Vision-Language Model for Embodied Int
        109118, -- 2608.12036 Mechanist: AI as a Scientific Instrument for Discovering the Mechanism
        109355, -- 2509.18216 nDNA -- the Semantic Helix of Artificial Cognition
        110058, -- 2506.12963 Reasoning Model Unlearning: Forgetting Traces, Not Just Answers, While
        111085, -- 2503.18008 Personalized Language Models via Privacy-Preserving Evolutionary Model
        111895, -- 2507.03382 Speaker-agnostic Emotion Vector for Cross-speaker Emotion Intensity Co
        112097, -- 2507.03377 Eigenvoice Synthesis based on Model Editing for Speaker Generation
        112551, -- 2408.06798 Token Compensator: Altering Inference Cost of Vision Transformer witho
        113336, -- 2407.03641 Learning Scalable Model Soup on a Single GPU: An Efficient Subspace Tr
        113971, -- 2609.05295 RISE: Recursive Improvement via Self-Extrapolating Policy Distillation
        114944, -- 2403.13341 FissionFusion: Fast Geometric Generation and Hierarchical Souping for
        116751, -- 2403.01753 Training-Free Pretrained Model Merging
        118147, -- 2607.19971 Unified Prediction and Planning via Conflict-Aware Disjoint Parameter
        118148, -- 2607.17467 DA-MergeLoRA: Hypernetwork-Based LoRA Merging for Few-Shot Test-Time D
        118170, -- 2512.01461 Stay Unique, Stay Efficient: Preserving Model Personality in Multi-Tas
        118180, -- 2606.26902 Learning to Recover Task Experts from a Multi-Task Merged Model
        118231, -- 2607.19384 SUM: Unified Geometric Surgery on Spatio-Temporal Adaptation Vectors f
        119445, -- 2511.20196 Towards Benign Memory Forgetting for Selective Multimodal Large Langua
        121951, -- 2609.14708 Lightning Weave: Improving the Accuracy-Efficiency Frontier of Reasoni
        122100, -- 2609.23377 One to More, More to One: Category-Aware Iterative Expert Training for
        122252, -- 2609.38154 LongLive-Plug: Once-for-All Distillation for Video Generation
        122288, -- 2609.34605 PMOPD: Task Ordering, Cycling, and Parameter-Update Subspace Protectio
        122314, -- 2609.29233 Post-Training Leaves Behavioral Shadows on Unrelated Decisions
        122316, -- 2609.35347 Beyond Teacher Assignment: Domain-Normalized Multi-Teacher On-Policy D
        122376, -- 2609.32821 Routing Drift Alone Does Not Diagnose Failure in Merged MoE LLMs
        122379, -- 2609.33437 SMAT: Simple and Efficient Merge-Aware Training
        122471, -- 2609.36484 The Teacher Is a Direction, Not a Destination: Extrapolating RL-Induce
        122656, -- 2609.39071 LexReward: A Taxonomy-Driven Reward Framework for Legal Language Model
        122676, -- 2609.33463 Rethinking Token Reweighting for SFT: Suppress, Reverse, and Extrapola
        122688, -- 2610.02381 Latent-MOPD: Latent Multi-Teacher On-Policy Distillation
        122692, -- 2610.02179 From Gradients to Capabilities: Understanding Multi-Teacher On-Policy
        122731, -- 2609.39420 QuantCode Model: Specializing Language Models for Executable Algorithm
        122874, -- 2610.10429 SGF+: Decoupling Gradient Flows for Autoregressive Video Generation
        122979, -- 2609.34344 Learning to Steer, Steering to See: Unveiling the Geometry of RLVR in
        123506, -- 2610.14270 The Thinking Leakage in Reinforcement Learning for LLMs
        123508, -- 2610.18638 To Align or Not To Align: Check Your COMPASS Before You Train
        123553, -- 2610.21055 Athanor: An Agent-Native System for Autonomous Post-Training Research
        123556, -- 2610.16784 InfoVis: Unified Slide Image Generation and Editing
        124136, -- 2602.08813 Robust Policy Optimization to Prevent Catastrophic Forgetting
        124206, -- 2606.00686 Dialectics of Alignment: Harnessing Unsafe Knowledge for Dynamic Safet
        124209, -- 2609.34348 Commutator Memory: Sparse, Path-Local Reading and Steering in Language
        124213, -- 2606.31963 Signed-Permutation Coordinate Transport for RMSNorm Transformers
        124428, -- 2610.19385 RA$^2$: Retain-Anchored Attraction Preserves Forget-Adjacent Utility i
        124434, -- 2604.27155 Generalizing the Geometry of Model Merging Through Fréchet Averages
        124549, -- 2607.20435 Making Open-Source Text LLM Watermarks Durable Against Merging
        124577, -- 2610.01054 Capturing In-Context Learning Dynamics with Task Operators
        124813, -- 2610.04792 Do More Modalities Always Help? A Geometric Perspective on Missing-Mod
        124824, -- 2508.21421 Rethinking Layer-wise Model Merging through Chain of Merges
        125259, -- 2603.14405 ES-Merging: Biological MLLM Merging via Embedding Space Signals
        125498, -- 2605.20262 Residual Paving: Diagnosing the Routing Bottleneck in Selective Refusa
        125529, -- 2609.31140 Can Linguistic Reasoning Vectors Enhance Multimodal Reasoning Ability?
        125544, -- 2510.04217 MLLMEraser: Achieving Test-Time Unlearning in Multimodal Large Languag
        126023, -- 2605.14084 CRANE: Constrained Reasoning Injection for Code Agents via Nullspace E
        126024, -- 2610.05025 Triggering Generalist Reasoning via Predictive Uncertainty for Dual-Sy
        126595, -- 2604.05502 AttnDiff: Attention-based Differential Fingerprinting for Large Langua
        126765, -- 2610.14558 PGSB: Pretrained-Guided Shared Basis for LoRA Model Merging
        126954, -- 2605.06632 Crafting Reversible SFT Behaviors in Large Language Models
        127316, -- 2605.12960 DiM$^3$: Bridging Multilingual and Multimodal Models via Direction- an
        127700, -- 2605.18309 Alignment Dynamics in LLM Fine-Tuning
        127926, -- 2606.06667 The Piggyback Hypothesis of Generalization: Explaining and Mitigating
        128276, -- 2605.12384 Scalable Token-Level Hallucination Detection in Large Language Models
        128335, -- 2606.23607 Scaling Linear Mode Connectivity and Merging to Billion Parameter Pret
        128386, -- 2602.11717 Beyond Parameter Arithmetic: Sparse Complementary Fusion for Distribut
        128662, -- 2609.37076 UnlearningSoup: Is Repeated Tuning Necessary for Large Language Model
        128667, -- 2610.01238 Mixture-Trained Merging for Unified Multi-Objective Models
        128703, -- 2606.00357 From “Weak” Signals to Strong Models: Preference Delta Aggregation wit
        128946, -- 2602.08901 Mitigating Memorization Where It Happens
        129118, -- 2605.07482 SHRED: Retain-Set-Free Unlearning via Self-Distillation with Logit Dem
        129214, -- 2605.31494 Consolidating Rewarded Perturbations for LLM Post-Training
        129597, -- 2604.20985 Differentially Private Model Merging
        129753, -- 2605.20730 Distributional Alignment as a Criterion for Designing Task Vectors in
        129829, -- 2609.31356 Open Vocabulary Domain Unlearning
        129972, -- 2610.16664 Making LoRA Identifiable: Orthogonal Alignment for Continual Learning
        130022, -- 2602.18658 Communication-Efficient Personalized Adaptation via Federated-Local Mo
        130800, -- 2604.03420 Zero-Shot Quantization via Weight-Space Arithmetic
        131879, -- 2611.05609 On the Generalization Limitation of On-Policy Distillation for Post-RL
        131985, -- 2611.09382 Exploring Weight-Space Programming: Capabilities, Generalization, and
        132071  -- 2611.09634 Steerable Multi-Objective Group-Relative Preference Optimization with
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
        16873, -- 2306.01708 TIES-Merging: Resolving Interference When Merging Models
        37885, -- 2410.03617 What Matters for Model Merging at Scale?
        38288, -- 2410.08371 Merging in a Bottle: Differentiable Adaptive Merging (DAM) and the Pat
        46825, -- 2503.21088 ZJUKLAB at SemEval-2025 Task 4: Unlearning via Model Merging
        57588, -- 2604.16826 Crowded in B-Space: Calibrating Shared Directions for LoRA Merging
        82972, -- 2509.24244 Model Merging Scaling Laws in Large Language Models
        83402, -- 2605.16882 E-PMQ: Expert-Guided Post-Merge Quantization with Merged-Weight Anchor
        85896  -- 2505.14009 Activation-Guided Consensus Merging for Large Language Models
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
        18607, -- 2307.13269 LoraHub: Efficient Cross-Task Generalization via Dynamic LoRA Composit
        23404, -- 2311.09344 Language and Task Arithmetic with Parameter-Efficient Layers for Zero-
        23650, -- 2311.13171 ComPEFT: Compression for Communicating Parameter Efficient Updates via
        24582, -- 2312.06173 Concrete Subspace Learning based Interference Elimination for Multi-ta
        24641, -- 2312.06795 Model Breadcrumbs: Scaling Multi-Task Model Merging with Sparse Masks
        27069, -- 2402.05859 Learning to Route Among Specialized Experts for Zero-Shot Generalizati
        27086, -- 2402.05966 Vanishing Feature: Diagnosing Model Merging and Beyond
        27951, -- 2402.16107 Knowledge Fusion of Chat LLMs: A Preliminary Technical Report
        27999, -- 2402.16828 Training Neural Networks from Scratch with Parallel Low-Rank Adapters
        28683, -- 2403.06952 SELMA: Learning and Merging Skill-Specific Text-to-Image Experts with
        28801, -- 2403.08763 Simple and Scalable Strategies to Continually Pre-train Large Language
        29160, -- 2403.13187 Evolutionary Optimization of Model Merging Recipes
        29616, -- 2403.19522 Model Stock: All we need is just a few fine-tuned models
        29864, -- 2404.02241 Linear Combination of Saved Checkpoints Makes Consistency and Diffusio
        30080, -- 2404.05590 MedExpQA: Multilingual Benchmarking of Large Language Models for Medic
        30386, -- 2404.09977 MaxFusion: Plug&Play Multi-Modal Generation in Text-to-Image Diffusion
        30654, -- 2404.14387 A Survey on Self-Evolution of Large Language Models
        30824, -- 2404.17401 Evaluation of Geographical Distortions in Language Models: A Crucial S
        30881, -- 2404.18466 HFT: Half Fine-Tuning for Large Language Models
        31249, -- 2405.07813 Localizing Task Information for Improved Model Merging and Compression
        31253, -- 2405.07883 Zero-Shot Tokenizer Transfer
        31303, -- 2405.09055 A safety realignment framework via subspace-oriented model fusion for
        31400, -- 2405.11157 Towards Modular LLMs by Building and Reusing a Library of LoRAs
        31495, -- 2405.13053 MeteoRA: Multiple-tasks Embedded LoRA for Large Language Models
        31550, -- 2405.14006 Evaluating Large Language Models with Human Feedback: Establishing a S
        31578, -- 2405.14366 MiniCache: KV Cache Compression in Depth Dimension for Large Language
        31600, -- 2405.14596 Linear Mode Connectivity in Differentiable Tree Ensembles
        31617, -- 2405.14768 WISE: Rethinking the Knowledge Memory for Lifelong Model Editing of La
        31893, -- 2405.17931 Online Merging Optimizers for Boosting Rewards and Mitigating Tax in A
        32056, -- 2405.19950 Multimodal Lego: Model Merging and Fine-Tuning Across Topologies and M
        32511, -- 2406.04927 LLM-based speaker diarization correction: A generalizable approach
        32690, -- 2406.07188 Merging Improves Self-Critique Against Jailbreak Attacks
        32732, -- 2406.07529 MAP: Low-compute Model Merging with Amortized Pareto Fronts via Quadra
        33098, -- 2406.11385 MetaGPT: Merging Large Language Models Using Model Exclusive Task Arit
        33154, -- 2406.11801 Safety Arithmetic: A Framework for Test-time Safety Alignment of Langu
        33194, -- 2406.12034 Self-MoE: Towards Compositional Large Language Models with Self-Specia
        33421, -- 2406.14563 Model Merging and Safety Alignment: One Bad Model Spoils the Bunch
        33493, -- 2406.15479 Twin-Merging: Dynamic Integration of Modular Expertise in Model Mergin
        33494, -- 2406.15480 On Giant's Shoulders: Effortless Weak to Strong by Dynamic Logits Fusi
        33597, -- 2406.16768 WARP: On the Benefits of Weight Averaged Rewarded Policies
        33694, -- 2406.17923 PAFT: A Parallel Training Paradigm for Effective LLM Fine-Tuning
        33870, -- 2407.00066 Compress then Serve: Serving Thousands of LoRA Adapters with Little Ov
        33970, -- 2407.01470 DogeRM: Equipping Reward Models with Domain Knowledge through Model Me
        34053, -- 2407.02447 PLeaS -- Merging Models with Permutations and Least Squares
        34077, -- 2407.02880 Knowledge Composition using Task Vectors with Learned Anisotropic Scal
        34160, -- 2407.03994 Unlocking the Potential of Model Merging for Low-Resource Languages
        34315, -- 2407.06089 Merge, Ensemble, and Cooperate! A Survey on Collaborative Strategies i
        34343, -- 2407.06322 MagMax: Leveraging Model Merging for Seamless Continual Learning
        34456, -- 2407.08056 Pareto Low-Rank Adapters: Efficient Multi-Task Learning with Preferenc
        34509, -- 2407.08699 Mitigating Catastrophic Forgetting in Language Transfer via Model Merg
        35007, -- 2407.15017 Knowledge Mechanisms in Large Language Models: A Survey and Perspectiv
        35588, -- 2408.03092 Extend Model Merging from Fine-Tuned to Pre-Trained Large Language Mod
        35697, -- 2408.04998 ProFuser: Progressive Fusion of Large Language Models
        35811, -- 2408.07057 A Survey on Model MoErging: Recycling and Routing Among Specialized Ex
        35844, -- 2408.07666 Model Merging in LLMs, MLLMs, and Beyond: Methods, Theories, Applicati
        35854, -- 2408.07990 FuseChat: Knowledge Fusion of Chat Models
        36245, -- 2408.14471 A Practitioner's Guide to Continual Multimodal Pretraining
        36314, -- 2408.15666 StyleRemix: Interpretable Authorship Obfuscation via Distillation and
        36333, -- 2408.15915 Leveraging Open Knowledge for Advancing Task Expertise in Large Langua
        36509, -- 2409.01483 Revisiting SMoE Language Models by Evaluating Inefficiencies with Task
        36606, -- 2409.03274 Recent Advances in Attack and Defense Approaches of Large Language Mod
        36852, -- 2409.08846 FP-VEC: Fingerprinting Large Language Models via Efficient Vector Addi
        37279, -- 2409.16167 Merging LoRAs like Playing LEGO: Pushing the Modularity of LoRA to Ext
        37514, -- 2409.19854 The Construction of Instruction-tuned LLMs for Finance without Instruc
        37637, -- 2410.01335 Layer Swapping for Zero-Shot Cross-Lingual Transfer in Large Language
        37669, -- 2410.01610 Upcycling Instruction Tuning from Dense to Mixture-of-Experts via Para
        37756, -- 2410.02396 Parameter Competition Balancing for Model Merging
        37906, -- 2410.03782 DaWin: Training-free Dynamic Weight Interpolation for Robust Adaptatio
        37984, -- 2410.04891 Low-Rank Continual Personalization of Diffusion Models
        38050, -- 2410.05583 NegMerge: Consensual Weight Negation for Strong Machine Unlearning
        38143, -- 2410.06664 Decouple-Then-Merge: Towards Better Training for Diffusion Models
        38194, -- 2410.07172 Glider: Global and Local Instruction-Driven Expert Router
        38218, -- 2410.07571 How Does Vision-Language Adaptation Impact the Safety of Vision Langua
        38299, -- 2410.08589 Retraining-Free Merging of Sparse MoE via Hierarchical Clustering
        38465, -- 2410.10801 Mix Data or Merge Models? Optimizing for Diverse Multi-Task Learning
        38618, -- 2410.12613 Exploring Model Kinship for Merging Large Language Models
        38704, -- 2410.13394 Cross-Lingual Auto Evaluation for Assessing Multilingual LLMs
        38753, -- 2410.13841 A Unified View of Delta Parameter Editing in Post-Trained Large-Scale
        38765, -- 2410.13910 Mitigating the Backdoor Effect for Multi-Task Model Merging via Safety
        38833, -- 2410.14735 Agent Skill Acquisition for Large Language Models via CycleQD
        39002, -- 2410.17146 LiNeS: Post-training Layer Scaling Prevents Forgetting and Enhances Mo
        39658, -- 2411.03055 ATM: Improving Model Merging by Alternating Tuning and Merging
        39782, -- 2411.05239 ZipNN: Lossless Compression for AI Models
        39998, -- 2411.09249 Enhancing Financial Domain Adaptation of Language Models via Model Aug
        41139, -- 2412.05148 LoRA.rar: Learning to Merge LoRAs via Hypernetworks for Subject-Style
        41554, -- 2412.10416 SUPERMERGE: An Approach For Gradient-Based Model Merging
        41561, -- 2412.10493 SafetyDPO: Scalable Safety Alignment for Text-to-Image Generation
        41646, -- 2412.11704 Vocabulary Expansion of Chat Models with Unlabeled Target Language Dat
        41977, -- 2412.15646 CustomTTT: Motion and Appearance Customized Video Generation via Test-
        42208, -- 2412.19098 Tint Your Models Task-wise for Improved Multi-task Model Merging
        42245, -- 2412.19726 Can Large Language Models Adapt to Other Agents In-Context?
        42411, -- 2501.01230 Modeling Multi-Task Model Merging as Adaptive Projective Gradient Desc
        43421, -- 2501.18512 Streaming DiLoCo with overlapping communication: Towards a Distributed
        43832, -- 2502.04959 No Task Left Behind: Isotropic Model Merging with Common and Task-Spec
        43882, -- 2502.05633 Mol-MoE: Training Preference-Guided Routers for Molecule Generation
        44051, -- 2502.07760 Scalable Fingerprinting of Large Language Models
        44220, -- 2502.10436 MERGE$^3$: Efficient Evolutionary Merging on Consumer-grade GPUs
        44229, -- 2502.10525 Towards Watermarking of Open-Source LLMs
        44246, -- 2502.10743 1bit-Merging: Dynamic Quantized Merging for Large Language Models
        44300, -- 2502.11191 Primus: A Pioneering Collection of Open-Source Datasets for Cybersecur
        44443, -- 2502.12420 Sens-Merging: Sensitivity-Guided Parameter Balancing for Merging Large
        44915, -- 2502.17159 Parameter Efficient Merging for Multimodal Large Language Models with
        45035, -- 2502.18635 Faster, Cheaper, Better: Multi-Objective Hyperparameter Optimization f
        45289, -- 2503.00948 Extrapolating and Decoupling Image-to-Video Generation Models: Motion
        45371, -- 2503.01874 CABS: Conflict-Aware and Balanced Sparsification for Enhancing Model M
        45497, -- 2503.03656 Robust Learning of Diverse Code Edits
        45547, -- 2503.04543 Keeping Yourself is Important in Downstream Tuning Multimodal Large La
        45737, -- 2503.06921 Task Vector Quantization for Memory-Efficient Model Merging
        46079, -- 2503.10633 Charting and Navigating Hugging Face's Model Atlas
        46211, -- 2503.12649 FW-Merging: Scaling Model Merging with Frank-Wolfe Optimization
        46766, -- 2503.20110 Efficient Model Development through Fine-tuning Transfer
        46799, -- 2503.20641 Unlocking Efficient Long-to-Short LLM Reasoning with Model Merging
        46839, -- 2503.21272 Reinforced Model Merging
        46913, -- 2503.22178 AdaRank: Adaptive Rank Pruning for Enhanced Model Merging
        47032, -- 2503.23733 AdaMMS: Model Merging for Heterogeneous Multimodal Large Language Mode
        47260, -- 2504.02890 Scaling Test-time Compute for Low-resource Languages: Multilingual Rea
        47468, -- 2504.07097 Sculpting Subspaces: Constrained Full Fine-Tuning in LLMs for Continua
        47485, -- 2504.07448 LoRI: Reducing Cross-Task Interference in Multi-Task Low-Rank Adaptati
        47609, -- 2504.09522 How new data permeates LLM knowledge and how to dilute it
        47995, -- 2504.15133 EasyEdit2: An Easy-to-use Steering Framework for Editing Large Languag
        48236, -- 2504.20859 X-Cross: Dynamic Integration of Language Models for Cross-Domain Seque
        48396, -- 2505.02410 Bielik 11B v2 Technical Report
        48539, -- 2505.05464 Bring Reason to Vision: Understanding Perception and Reasoning through
        48738, -- 2505.09610 Customizing a Large Language Model for VHDL Design of High-Performance
        48797, -- 2505.10717 A Modular Approach for Clinical SLMs Driven by Synthetic Data with Pre
        48865, -- 2505.11427 Mergenetic: a Simple Evolutionary Model Merging Library
        48887, -- 2505.11711 Reinforcement Learning Finetunes Small Subnetworks in Large Language M
        48924, -- 2505.12082 Model Merging in Pre-training of Large Language Models
        49102, -- 2505.13878 InfiFPO: Implicit Model Fusion via Preference Optimization in Large La
        49104, -- 2505.13893 InfiGFusion: Graph-on-Logits Distillation via Efficient Gromov-Wassers
        49235, -- 2505.14827 Text Generation Beyond Discrete Token Sampling
        49370, -- 2505.16151 Training-Free Reasoning and Reflection in MLLMs
        49388, -- 2505.16270 Transformer Copilot: Learning from The Mistake Log in LLM Fine-tuning
        49524, -- 2505.17496 Analyzing Mitigation Strategies for Catastrophic Forgetting in End-to-
        49619, -- 2505.18502 Knowledge Grafting of Large Language Models
        49775, -- 2505.19797 The Avengers: A Simple Recipe for Uniting Smaller Language Models to C
        49818, -- 2505.20144 SeMe: Training-Free Language Model Merging via Semantic Alignment
        50173, -- 2505.23844 Enabling Flexible Multi-LLM Integration for Scalable Knowledge Aggrega
        51103, -- 2506.12379 Training-free LLM Merging for Multi-task Learning
        51462, -- 2506.20480 GPTailor: Large Language Model Pruning Through Layer Cutting and Stitc
        51501, -- 2506.21260 DuET: Dual Incremental Object Detection via Exemplar-Free Task Arithme
        51578, -- 2506.23266 Sub-MoE: Efficient Mixture-of-Expert LLMs Compression via Subspace Exp
        51797, -- 2507.07024 FlexOlmo: Open Language Models for Flexible Data Use
        51816, -- 2507.07562 The Synergy Dilemma of Long-CoT SFT and RL: Investigating Post-Trainin
        52353, -- 2508.09945 VisCodex: Unified Multimodal Code Generation via Merging Vision and Co
        52382, -- 2508.11032 MedSAMix: A Training-Free Model Merging Approach for Medical Image Seg
        52391, -- 2508.11548 Copyright Protection for Large Language Models: A Survey of Methods, C
        52607, -- 2509.01363 Reasoning Vectors: Transferring Chain-of-Thought Capabilities via Task
        52695, -- 2509.06888 mmBERT: A Modern Multilingual Encoder with Annealed Language Learning
        52916, -- 2509.17786 Accurate and Efficient Low-Rank Model Merging in Core Space
        53194, -- 2510.01879 REPAIR: Robust Editing via Progressive Adaptive Intervention and Reint
        53588, -- 2510.09913 Don't Throw Away Your Pretrained Model
        53657, -- 2510.15110 DLER: Doing Length pEnalty Right - Incentivizing More Intelligence per
        53821, -- 2510.21223 Model Merging with Functional Dual Anchors
        54016, -- 2511.00062 World Simulation with Video Foundation Models for Physical AI
        54216, -- 2511.13254 Souper-Model: How Simple Arithmetic Unlocks State-of-the-Art LLM Perfo
        54590, -- 2512.04844 Mitigating Catastrophic Forgetting in Target Language Adaptation of LL
        54988, -- 2512.13043 GTR-Turbo: Merged Checkpoint is Secretly a Free Teacher for Agentic VL
        55159, -- 2601.05106 Token-Level LLM Collaboration via FusionRoute
        55391, -- 2601.14004 Locate, Steer, and Improve: A Practical Survey of Actionable Mechanist
        55730, -- 2602.00747 Decouple Searching from Training: Scaling Data Mixing via Model Mergin
        55948, -- 2602.09082 UI-Venus-1.5 Technical Report
        56057, -- 2602.09021 χ_{0}: Resource-Aware Robust Manipulation via Taming Distributional In
        56675, -- 2603.11510 Tiny Aya: Bridging Scale and Multilingual Depth
        56732, -- 2603.15590 Effective Distillation to Hybrid xLSTM Architectures
        57112, -- 2604.00007 Dynin-Omni: Omnimodal Unified Large Diffusion Language Model
        57380, -- 2604.02372 Backdoor Attacks on Decentralised Post-Training
        57415, -- 2604.05336 TRACE: Capability-Targeted Agentic Training
        57636, -- 2604.17078 Understanding and Enforcing Weight Disentanglement in Task Arithmetic
        57891, -- 2512.09972 AP-BMM: Approximating Capability-Efficiency Pareto Sets of LLMs via As
        57927, -- 2604.21637 Multilinguality at the Edge: Developing Language Models for the Global
        58696, -- 2603.29765 Training-Free Dynamic Upcycling of Expert Language Models
        58783, -- 2603.12681 Colluding LoRA: A Compositional Vulnerability in LLM Safety Alignment
        58798, -- 2511.21437 A Systematic Study of In-the-Wild Model Merging for Large Language Mod
        58980, -- 2603.22755 KALAVAI: Predicting When Independent Specialist Fusion Works -- A Quan
        58986, -- 2603.23408 GeoSANE: Learning Geospatial Representations from Models, Not Data
        59780, -- 2603.06242 DC-Merge: Improving Model Merging with Directional Consistency
        59858, -- 2603.04972 Functionality-Oriented LLM Merging on the Fisher--Rao Manifold
        60404, -- 2602.17385 Dataless Weight Disentanglement in Task Arithmetic via Kronecker-Facto
        60484, -- 2603.06610 CapTrack: Multifaceted Evaluation of Forgetting in LLM Post-Training
        60731, -- 2602.12566 To Mix or To Merge: Toward Multi-Domain Reinforcement Learning for Lar
        60745, -- 2602.12323 The Appeal and Reality of Recycling LoRAs with Adaptive Merging
        61152, -- 2602.05787 Bagging-Based Model Merging for Robust General Text Embeddings
        61197, -- 2602.05943 Orthogonal Model Merging
        61236, -- 2602.04937 Linear Model Merging Unlocks Simple and Scalable Multimodal Data Mixtu
        61245, -- 2602.04521 C-ΔΘ: Circuit-Restricted Weight Arithmetic for Selective Refusal
        61320, -- 2602.03696 Conflict-Resolving and Sharpness-Aware Minimization for Generalized Kn
        61624, -- 2602.00585 Exploring Information Seeking Agent Consolidation
        62070, -- 2601.17858 MergeMix: Optimizing Mid-Training Data Mixtures via Learnable Model Me
        62312, -- 2601.13580 Neural Organ Transplantation (NOT): Checkpoint-Based Modular Adaptatio
        62447, -- 2601.10804 BYOL: Bring Your Own Language Into LLMs
        62658, -- 2601.07309 ARM: Role-Conditioned Neuron Transplantation for Training-Free General
        63946, -- 2512.08333 Robust Finetuning of Vision-Language-Action Robot Policies via Paramet
        64096, -- 2512.05117 The Universal Weight Subspace Hypothesis
        64633, -- 2511.18810 MergeVLA: Cross-Skill Model Merging Toward a Generalist Vision-Languag
        65154, -- 2511.08484 Patching LLM Like Software: A Lightweight Method for Improving Safety
        65587, -- 2510.27265 T3: Test-Time Model Merging in VLMs for Zero-Shot Medical Imaging Anal
        66346, -- 2510.14163 Towards Reversible Model Merging For Low-rank Weights
        66351, -- 2510.13999 REAP the Experts: Why Pruning Prevails for One-Shot MoE compression
        66403, -- 2510.13537 K-Merge: Online Continual Merging of Adapters for On-device Large Lang
        66711, -- 2510.08396 FlyLoRA: Boosting Task Decoupling and Parameter Efficiency via Implici
        66877, -- 2510.09658 Gradient-Sign Masking for Task Vector Transport Across Pre-Trained Mod
        66920, -- 2510.05064 Boomerang Distillation Enables Zero-Shot Model Size Interpolation
        67208, -- 2510.00810 Family Matters: Language Transfer and Merging for Adapting Small LLMs
        67360, -- 2509.25712 Expert Merging: Model Merging with Unsupervised Expert Alignment and I
        67593, -- 2509.23381 Guard Vector: Beyond English LLM Guardrails with Task-Vector Compositi
        67793, -- 2509.21164 Mixture of Thoughts: Learning to Aggregate What Experts Think, Not Jus
        67951, -- 2509.18883 LongCat-Flash-Thinking Technical Report
        68323, -- 2509.12951 Black-box Model Merging for Language-Model-as-a-Service with Massive M
        68408, -- 2509.11414 Continually Adding New Languages to Multilingual Language Models
        68424, -- 2509.11167 Harnessing Optimization Dynamics for Curvature-Informed Model Merging
        68465, -- 2509.10105 VARCO-VISION-2.0 Technical Report
        68866, -- 2509.01548 Model Unmerging: Making Your Models Unmergeable for Secure Model Shari
        68968, -- 2509.00309 Balanced Actor Initialization: Stable RLHF Training of Distillation-Ba
        69131, -- 2508.19353 Efficient Multi-Source Knowledge Transfer by Model Merging
        69329, -- 2508.16204 Competition and Attraction Improve Model Fusion
        69337, -- 2508.16082 On Task Vectors and Gradients
        69351, -- 2508.15706 Communication Efficient LLM Pre-training with SparseLoCo
        69360, -- 2508.15507 Think in Blocks: Adaptive Reasoning from Direct Response to Deep Reaso
        69546, -- 2508.12622 Consiglieres in the Shadow: Understanding the Use of Uncensored Large
        69559, -- 2508.12491 Cost-Aware Contrastive Routing for LLMs
        70136, -- 2508.04153 ICM-Fusion: In-Context Meta-Optimized LoRA Fusion for Multi-Task Adapt
        70224, -- 2508.03140 RCP-Merging: Merging Long Chain-of-Thought Models with Domain-Specific
        70226, -- 2508.03121 RegMean++: Enhancing Effectiveness and Generalization of Regression Me
        70379, -- 2508.01148 DisTaC: Conditioning Task Vectors via Distillation for Robust Model Me
        70717, -- 2507.19390 ReCatcher: Towards LLMs Regression Testing for Code Generation
        70974, -- 2507.14783 Omni-Thinker: Scaling Cross-Domain Generalization in LLMs via Multi-Ta
        71763, -- 2506.19140 Command-V: Pasting LLM Behaviors via Activation Profiles
        71860, -- 2506.16506 Subspace-Boosted Model Merging
        72272, -- 2506.15721 Bohdi: Heterogeneous LLM Fusion with Automatic Data Exploration
        72472, -- 2506.14794 Assembly of Experts: Linear-time construction of the Chimera LLM varia
        72556, -- 2505.23117 Decom-Renorm-Merge: Model Merging on the Right Space Improves Multitas
        72568, -- 2505.22635 Learning Composable Chains-of-Thought
        72881, -- 2505.15875 Decouple and Orthogonalize: A Data-Free Framework for LoRA Merging
        72937, -- 2505.14136 Local Mixtures of Experts: Essentially Free Test-Time Training via Mod
        73051, -- 2505.10833 MergeBench: A Benchmark for Merging Domain-Specialized LLMs
        73297, -- 2504.20106 Adaptive Helpfulness-Harmlessness Alignment with Preference Vectors
        74614, -- 2502.12776 Portable Reward Tuning: Towards Reusable Fine-Tuning across Different
        75679, -- 2411.18607 Task Arithmetic Through The Lens Of One-Shot Federated Learning
        75690, -- 2412.00081 Task Singular Vectors: Reducing Task Interference in Model Merging
        76017, -- 2410.13569 Learning on Model Weights using Tree Experts
        76031, -- 2410.13025 LoRA Soups: Merging LoRAs for Practical Skill Composition Tasks
        76068, -- 2410.09982 Self-Data Distillation for Recovering Quality in Pruned Large Language
        76075, -- 2410.09508 CollabEdit: Towards Non-destructive Collaborative Knowledge Editing
        76267, -- 2405.17461 EMR-Merging: Tuning-Free High-Performance Model Merging
        76524, -- 2408.13656 Localize-and-Stitch: Efficient Model Merging via Sparse Task Arithmeti
        76865, -- 2407.00487 It's Morphing Time: Unleashing the Potential of Multiple LLMs via Mult
        77195, -- 2405.16350 A Second-Order Perspective on Model Compositionality and Incremental L
        83135, -- 2605.13030 FeatCal: Feature Calibration for Post-Merging Models
        83169, -- 2605.14386 Darwin Family: MRI-Trust-Weighted Evolutionary Merging for Training-Fr
        83875, -- 2605.28819 PEFT-Arena: Understanding Parameter-Efficient Finetuning from a Stabil
        84141, -- 2510.27316 Parameterized Prompt for Incremental Object Detection
        84161, -- 2511.11851 Defending Unauthorized Model Merging via Dual-Stage Weight Protection
        84313, -- 2512.02441 Basis-Oriented Low-rank Transfer for Few-Shot and Test-Time Adaptation
        84525, -- 2602.18845 Echoes of Ownership: Adversarial-Guided Dual Injection for Copyright P
        84572, -- 2602.20208 Model Merging in the Essential Subspace
        84721, -- 2603.02945 ACE-Merging: Data-Free Model Merging with Adaptive Covariance Estimati
        84737, -- 2603.03920 BD-Merging: Bias-Aware Dynamic Model Merging with Evidence-Guided Cont
        84767, -- 2603.05768 Bridging Domains through Subspace-Aware Model Merging
        84841, -- 2603.10526 Sparse Task Vector Mixup with Hypernetworks for Efficient Knowledge Tr
        84875, -- 2603.12433 Revisiting Model Stitching In the Foundation Model Era
        85147, -- 2603.26299 Preference-Aligned LoRA Merging: Preserving Subspace Coverage and Addr
        85148, -- 2603.26317 Label-Free Cross-Task LoRA Merging with Null-Space Compression
        85755, -- 2510.11268 Exploring and Leveraging Class Vectors for Classifier Editing
        85773, -- 2505.11883 MINGLE: Mixtures of Null-Space Gated Low-Rank Experts for Test-Time Co
        86036, -- 2509.18208 Variational Task Vector Composition
        86158, -- 2505.22860 Permissioned LLMs: Enforcing Access Control in Large Language Models
        86654, -- 2505.16524 CodeMerge: Codebook-Guided Model Merging for Robust Test-Time Adaptati
        86801, -- 2505.23859 Towards Minimizing Feature Drift in Model Merging: Layer-wise Task Vec
        87068, -- 2505.22389 Train with Perturbation, Infer after Merging: A Two-Stage Framework fo
        87151, -- 2502.04510 Heterogeneous Swarms: Jointly Optimizing Model Roles and Weights for M
        87172, -- 2503.09271 DitHub: A Modular Framework for Incremental Open-Vocabulary Object Det
        87247, -- 2409.18893 HM3: Hierarchical Multi-Objective Model Merging for Pretrained Models
        87728, -- 2503.07661 Disrupting Model Merging: A Parameter-Level Defense Without Sacrificin
        88016, -- 2507.04790 Interaction-Merged Motion Planning: Effectively Leveraging Diverse Mot
        89182, -- 2505.06977 CAT Merging: A Training-Free Approach for Resolving Conflicts in Model
        89257, -- 2410.11163 Model Swarms: Collaborative Search to Adapt LLM Experts via Swarm Inte
        89374, -- 2505.22697 Update Your Transformer to the Latest Release: Re-Basin of Task Vector
        89694, -- 2502.12706 Scalable Model Merging with Progressive Layer-wise Distillation
        89866, -- 2503.08099 Whoever Started the interference Should End It: Guiding Data-Free Mode
        89945, -- 2507.04119 When Data-Free Knowledge Distillation Meets Non-Transferable Teacher:
        89963, -- 2502.17298 Delta Decompression for MoE-based LLMs Compression
        89964, -- 2504.02666 BECAME: Bayesian Continual Learning with Adaptive Model Merging
        90020, -- 2502.00264 Beyond the Permutation Symmetry of Transformers: The Role of Rotation
        90149, -- 2503.15842 FedAWA: Adaptive Optimization of Aggregation Weights in Federated Lear
        90711, -- 2412.18219 Adapter Merging with Centroid Prototype Mapping for Scalable Class-Inc
        90727, -- 2411.15231 IterIS: Iterative Inference-Solving Alignment for LoRA Merging
        90950, -- 2412.06712 How to Merge Your Multimodal Models Over Time?
        91000, -- 2503.14897 When Domain Generalization meets Generalized Category Discovery: An Ad
        91049, -- 2412.06619 Copyright-Protected Language Generation via Adaptive Model Fusion
        91125, -- 2410.19735 Model merging with SVD to tie the Knots
        91576, -- 2410.17961 Closed-Form Merging of Parameter-Efficient Modules for Federated Conti
        92468, -- 2606.02398 A Local Perturbation Theory for Cross-Domain Interference and Recovery
        92472, -- 2606.01717 Decentralized Instruction Tuning: Conflict-Aware Splitting and Weight
        92559, -- 2605.29489 Access Sets Matter: Budgeting Expert Reads for Scalable Weight-Space M
        92620, -- 2510.08023 Do We Really Need Permutations? Impact of Model Width on Linear Mode C
        92644, -- 2511.05408 Steering Language Models with Weight Arithmetic
        92745, -- 2512.23017 Merge before Forget: A Single LoRA Continual Learning via Continual Me
        92841, -- 2504.05342 MASS: MoErging through Adaptive Subspace Selection
        93204, -- 2602.22538 RAIN-Merging: A Gradient-Free Method to Enhance Instruction Following
        93367, -- 2603.09888 LCA: Local Classifier Alignment for Continual Learning
        93420, -- 2603.01526 Scalable Multi-Task Low-Rank Model Adaptation
        93430, -- 2505.23209 Navigating the Accuracy-Size Trade-Off with Flexible Model Merging
        93460, -- 2504.05902 Defending against Backdoor Attacks via Module Switching
        93502, -- 2601.19503 GradPruner: Gradient-guided Layer Pruning Enabling Efficient Fine-Tuni
        93700, -- 2509.23487 Temporal Generalization: A Reality Check
        93904, -- 2506.20746 Dynamic Weight Grafting: Localizing Finetuned Factual Knowledge in Tra
        93932, -- 2503.10705 Enhanced Continual Learning of Vision-Language Models with Model Fusio
        94067, -- 2510.04686 How does the optimizer implicitly bias the model merging loss landscap
        94277, -- 2505.20925 Multi-objective Large Language Model Alignment with Hierarchical Exper
        94286, -- 2502.07274 Forget Forgetting: Continual Learning in a World of Abundant Memory
        94513, -- 2510.17776 Mapping Post-Training Forgetting in Language Models at Scale
        94561, -- 2511.07970 Continual Unlearning for Text-to-Image Diffusion Models: A Regularizat
        94791, -- 2601.10497 MergeTune: Continued Fine-Tuning of Vision-Language Models
        94919, -- 2512.04695 Trinity: An Evolved LLM Coordinator
        94926, -- 2509.21413 Null-Space Filtering for Data-Free Continual Model Merging: Preserving
        95096, -- 2606.05846 Towards Truly Multilingual ASR: Generalizing Code-Switching ASR to Uns
        98846, -- 2606.27377 DanceOPD: On-Policy Generative Field Distillation
        98887, -- 2606.26080 Neglected Free Lunch from Post-training: Progress Advantage for LLM Ag
        99021, -- 2606.30406 MOPD: Multi-Teacher On-Policy Distillation for Capability Integration
        99039, -- 2607.00666 Domain Arithmetic: One-Shot VLA Adaptation under Environmental Shifts
        99099, -- 2607.01686 WARP: Weight-Space Analysis for Recovering Training Data Portfolios
        99141, -- 2601.21187 FRISM: Fine-Grained Reasoning Injection via Subspace-Level Model Mergi
        99190, -- 2602.05536 When Shared Knowledge Hurts: Spectral Over-Accumulation in Model Mergi
        99314, -- 2605.29295 EvoGM: Learning to Merge LLMs via Evolutionary Generative Optimization
        99606, -- 2605.14289 MetaMoE: Diversity-Aware Proxy Selection for Privacy-Preserving Mixtur
        99736, -- 2606.10617 SSR-Merge: Subspace Signal Routing for Training-Free LoRA Merging in D
        99820, -- 2605.26484 Extra-Merge: Tracing the Rank-1 Subspace of Model Merging in Language
        99824, -- 2606.25761 Bridging Spherical Black-Box Optimizers
        100230, -- 2601.22285 Demystifying Mergeability: Interpretable Properties to Predict Model M
        100331, -- 2605.24550 Jailbreak to Protect: Buffering and Reinforcing via Temporary Jailbrea
        100371, -- 2510.08977 Breaking the Self-Confirming Loop: Diagnosing and Mitigating Systemic
        100452, -- 2606.12498 From Parameters to Feature Space: Task Arithmetic for Backdoor Mitigat
        100636, -- 2605.19409 Unlocking the Potential of Continual Model Merging: An ODE Perspective
        100738, -- 2605.22350 Partial Fusion of Neural Networks: Efficient Tradeoffs Between Ensembl
        100755, -- 2606.16501 Post-Hoc Merging is Not Enough: Many-Shot Model Merging with Loss-Gap
        100831, -- 2606.03723 Compress then Merge: From Multiple LoRAs into One Low-Rank Adapter
        100906, -- 2602.12952 Transporting Task Vectors across Different Architectures without Train
        101126, -- 2605.28577 Continual Model Routing in Evolving Model Hubs
        101280, -- 2603.01097 Understanding LoRA as Knowledge Memory: An Empirical Analysis
        101546, -- 2601.21898 Making Models Unmergeable via Scaling-Sensitive Loss Landscape
        101653, -- 2606.03232 GFFMERGE: Efficient Merging of Graph Neural Force Fields and Beyond
        101661, -- 2606.00511 Saliency-Aware Model Merging
        101985, -- 2506.14126 From Memorization to Parameter Interference: How Overtraining Experts
        102205, -- 2602.02890 Self-Soupervision: Cooking Model Soups without Labels
        102346, -- 2602.09689 MODEL SOUPS NEED ONLY ONE INGREDIENT
        102461, -- 2605.23410 What Linear Probes Miss: Multi-View Probing for Weight-Space Learning
        102570, -- 2607.04425 UI-MOPD: Multi-Platform On-Policy Distillation for Continual GUI Agent
        102889, -- 2601.04262 Safety-Utility Conflicts Are Not Global: Surgical Alignment via Head-L
        103092, -- 2502.04506 When One LLM Drools, Multi-LLM Collaboration Rules
        103714, -- 2505.21226 Why Do More Experts Fail? A Theoretical Analysis of Model Merging
        104051, -- 2607.03065 Spectral Rewiring for Exploration, Purification, and Model Merging
        104452, -- 2607.19331 ISO: An RLVR-Native Optimization Stack
        104536, -- 2605.20296 Spectral Unforgetting: Post-Hoc Recovery of Damaged Capabilities Witho
        104771, -- 2601.18585 GimmBO: Interactive Generative Image Model Merging via Bayesian Optimi
        105401, -- 2503.01164 Med-LEGO: Editing and Adapting toward Generalist Medical Image Diagnos
        105595, -- 2507.00292 Reducing Variability of Multiple Instance Learning Methods for Digital
        105646, -- 2503.07799 Self-supervised Normality Learning and Divergence Vector-guided Model
        106255, -- 2604.01329 Model Merging via Data-Free Covariance Estimation
        106291, -- 2606.30044 Building Multi-Task Agentic LLMs via Two-Phase Distillation
        106321, -- 2604.06465 Multi-objective Evolutionary Merging Enables Efficient Reasoning Model
        107228, -- 2511.10712 Do Not Merge My Model! Safeguarding Open-Source LLMs Against Unauthori
        107549, -- 2511.17987 Escaping Optimization Stagnation: Taking Steps Beyond Task Arithmetic
        107727, -- 2509.18542 Symphony-MoE: Harmonizing Disparate Pre-trained Models into a Coherent
        107959, -- 2506.05577 Policy Search, Retrieval, and Composition via Task Similarity in Colla
        108383, -- 2602.08564 M-Loss: Quantifying Model Merging Compatibility with Limited Unlabeled
        108571, -- 2511.06390 Ghost in the Transformer: Detecting Model Reuse with Invariant Spectra
        108781, -- 2605.10903 CapVector: Learning Transferable Capability Vectors in Parametric Spac
        108791, -- 2605.12419 ORBIT: Preserving Foundational Language Capabilities in GenRetrieval v
        108939, -- 2608.06216 Continual Learning in Transition
        108974, -- 2608.03573 SFT Conflicts, RL Coexists: A Theoretical and Empirical Analysis of Mu
        108983, -- 2608.06756 Capek 0.5: An Execution-Centric Vision-Language Model for Embodied Int
        109088, -- 2608.08627 UniMoMo: Expert Merging-Based MoE Acceleration for Large Recommendatio
        109530, -- 2608.20281 Inject, Align, Recover: Staged Post-Training for Retrieval-Free Docume
        109717, -- 2608.24053 WeMM-Embedding: WeChat Multi-Modal Embedding Technical Report
        110347, -- 2503.07663 Merge then Realign: Simple and Effective Modality-Incremental Continua
        110733, -- 2505.18548 Composable Cross-prompt Essay Scoring by Merging Models
        110817, -- 2507.17706 HydraOpt: Navigating the Efficiency-Performance Trade-off of Adapter M
        110861, -- 2507.16083 Efficient Compositional Multi-tasking for On-device Large Language Mod
        110938, -- 2505.21963 LaMDAgent: An Autonomous Framework for Post-Training Pipeline Optimiza
        111085, -- 2503.18008 Personalized Language Models via Privacy-Preserving Evolutionary Model
        111809, -- 2505.13270 Distilling a speech and music encoder with task arithmetic
        111895, -- 2507.03382 Speaker-agnostic Emotion Vector for Cross-speaker Emotion Intensity Co
        112097, -- 2507.03377 Eigenvoice Synthesis based on Model Editing for Speaker Generation
        113870, -- 2609.01572 From Production Traffic to Post-Training: Building a Self-Hosted LLM T
        113936, -- 2608.26730 Knowing When Not to Reuse: Conditional Experience Transfer in Autonomo
        114206, -- 2609.11977 Occamy-1.0: Open Pareto-frontier 35B Intelligence for Co-work
        118147, -- 2607.19971 Unified Prediction and Planning via Conflict-Aware Disjoint Parameter
        118148, -- 2607.17467 DA-MergeLoRA: Hypernetwork-Based LoRA Merging for Few-Shot Test-Time D
        118150, -- 2602.06043 Shared LoRA Subspaces for almost Strict Continual Learning
        118166, -- 2606.22589 Training-Free Task Classification for Multi-Task Model Merging
        118170, -- 2512.01461 Stay Unique, Stay Efficient: Preserving Model Personality in Multi-Tas
        118180, -- 2606.26902 Learning to Recover Task Experts from a Multi-Task Merged Model
        118210, -- 2606.30360 On the Vulnerability of Parameter-Level Defenses to Model Merging
        118231, -- 2607.19384 SUM: Unified Geometric Surgery on Spatio-Temporal Adaptation Vectors f
        119445, -- 2511.20196 Towards Benign Memory Forgetting for Selective Multimodal Large Langua
        121951, -- 2609.14708 Lightning Weave: Improving the Accuracy-Efficiency Frontier of Reasoni
        122376, -- 2609.32821 Routing Drift Alone Does Not Diagnose Failure in Merged MoE LLMs
        122379, -- 2609.33437 SMAT: Simple and Efficient Merge-Aware Training
        122443, -- 2609.22237 Not All Ranks Are Equal: Budget-Aware LoRA Merging Across Tasks
        122676, -- 2609.33463 Rethinking Token Reweighting for SFT: Suppress, Reverse, and Extrapola
        122874, -- 2610.10429 SGF+: Decoupling Gradient Flows for Autoregressive Video Generation
        123508, -- 2610.18638 To Align or Not To Align: Check Your COMPASS Before You Train
        123553, -- 2610.21055 Athanor: An Agent-Native System for Autonomous Post-Training Research
        123674, -- 2606.19037 Querit-Reranker: Training Compact Multilingual Rerankers via Efficient
        123874, -- 2610.25078 CoEvo-RSI: When Harnesses Evolve, Which Models Should Follow?
        124213, -- 2606.31963 Signed-Permutation Coordinate Transport for RMSNorm Transformers
        124434, -- 2604.27155 Generalizing the Geometry of Model Merging Through Fréchet Averages
        124549, -- 2607.20435 Making Open-Source Text LLM Watermarks Durable Against Merging
        124661, -- 2609.31784 Witness Overlap: Directional Provenance Inside Open-Weight Model Famil
        124824, -- 2508.21421 Rethinking Layer-wise Model Merging through Chain of Merges
        125035, -- 2607.03011 Can Model Merging Improve Aggregation in DiLoCo?
        125259, -- 2603.14405 ES-Merging: Biological MLLM Merging via Embedding Space Signals
        126023, -- 2605.14084 CRANE: Constrained Reasoning Injection for Code Agents via Nullspace E
        126024, -- 2610.05025 Triggering Generalist Reasoning via Predictive Uncertainty for Dual-Sy
        126406, -- 2609.09054 Training-Free Task Vectors for LLM Behavioral Control
        126595, -- 2604.05502 AttnDiff: Attention-based Differential Fingerprinting for Large Langua
        126765, -- 2610.14558 PGSB: Pretrained-Guided Shared Basis for LoRA Model Merging
        127316, -- 2605.12960 DiM$^3$: Bridging Multilingual and Multimodal Models via Direction- an
        128102, -- 2605.18904 Dynamic Model Merging Made Slim
        128230, -- 2609.32332 When the Merge Coefficient Stops Mattering: Proximity Regularized Merg
        128276, -- 2605.12384 Scalable Token-Level Hallucination Detection in Large Language Models
        128386, -- 2602.11717 Beyond Parameter Arithmetic: Sparse Complementary Fusion for Distribut
        128667, -- 2610.01238 Mixture-Trained Merging for Unified Multi-Objective Models
        128703, -- 2606.00357 From “Weak” Signals to Strong Models: Preference Delta Aggregation wit
        129214, -- 2605.31494 Consolidating Rewarded Perturbations for LLM Post-Training
        129597, -- 2604.20985 Differentially Private Model Merging
        129972, -- 2610.16664 Making LoRA Identifiable: Orthogonal Alignment for Continual Learning
        130022, -- 2602.18658 Communication-Efficient Personalized Adaptation via Federated-Local Mo
        130267, -- 2605.09879 M2A: Synergizing Mathematical and Agentic Reasoning in Large Language
        130491, -- 2609.39836 Spherical Interpolation for Backward-Compatible Multimodal Representat
        130800, -- 2604.03420 Zero-Shot Quantization via Weight-Space Arithmetic
        131879, -- 2611.05609 On the Generalization Limitation of On-Policy Distillation for Post-RL
        131995, -- 2611.03953 P^2-MOPD: Accelerating Multi-Teacher On-Policy Distillation via Parame
        132071  -- 2611.09634 Steerable Multi-Objective Group-Relative Preference Optimization with
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
        22987, -- 2311.03099 Language Models are Super Mario: Absorbing Abilities from Homologous M
        33123, -- 2406.11617 DELLA-Merging: Reducing Interference in Model Merging through Magnitud
        38288, -- 2410.08371 Merging in a Bottle: Differentiable Adaptive Merging (DAM) and the Pat
        38350, -- 2410.09344 DARE the Extreme: Revisiting Delta-Parameter Pruning For Fine-Tuned Mo
        38753, -- 2410.13841 A Unified View of Delta Parameter Editing in Post-Trained Large-Scale
        82972, -- 2509.24244 Model Merging Scaling Laws in Large Language Models
        102983  -- 2605.19523 Investigating Cross-Modal Skill Injection: Scenarios, Methods, and Hyp
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
        22743, -- 2310.19347 Improving Factual Consistency of Text Summarization by Adversarially D
        23341, -- 2311.08692 Routing to the Expert: Efficient Reward-guided Ensemble of Large Langu
        23650, -- 2311.13171 ComPEFT: Compression for Communicating Parameter Efficient Updates via
        23668, -- 2311.13534 LM-Cocktail: Resilient Tuning of Language Models via Model Merging
        24511, -- 2312.05215 DeltaZip: Efficient Serving of Multiple Full-Model-Tuned LLMs
        24582, -- 2312.06173 Concrete Subspace Learning based Interference Elimination for Multi-ta
        26155, -- 2401.12255 Instructional Fingerprinting of Large Language Models
        26788, -- 2402.02705 Representation Surgery for Multi-Task Model Merging
        27380, -- 2402.10193 BitDelta: Your Fine-Tune May Only Be Worth One Bit
        27393, -- 2402.10373 BioMistral: A Collection of Open-Source Pretrained Large Language Mode
        27475, -- 2402.11187 LaCo: Large Language Model Pruning via Layer Collapse
        27537, -- 2402.11746 Language Models are Homer Simpson! Safety Re-Alignment of Fine-tuned L
        27641, -- 2402.12750 Model Composition for Multimodal Large Language Models
        27951, -- 2402.16107 Knowledge Fusion of Chat LLMs: A Preliminary Technical Report
        28683, -- 2403.06952 SELMA: Learning and Merging Skill-Specific Text-to-Image Experts with
        29160, -- 2403.13187 Evolutionary Optimization of Model Merging Recipes
        29168, -- 2403.13257 Arcee's MergeKit: A Toolkit for Merging Large Language Models
        29864, -- 2404.02241 Linear Combination of Saved Checkpoints Makes Consistency and Diffusio
        29990, -- 2404.04067 Does Biomedical Training Lead to Better Medical Performance?
        30080, -- 2404.05590 MedExpQA: Multilingual Benchmarking of Large Language Models for Medic
        30409, -- 2404.10306 Balancing Speciality and Versatility: a Coarse to Fine Framework for S
        30460, -- 2404.11225 In-Context Learning State Vector with Inner and Momentum Optimization
        30654, -- 2404.14387 A Survey on Self-Evolution of Large Language Models
        30789, -- 2404.16792 Weak-to-Strong Extrapolation Expedites Alignment
        30824, -- 2404.17401 Evaluation of Geographical Distortions in Language Models: A Crucial S
        30881, -- 2404.18466 HFT: Half Fine-Tuning for Large Language Models
        31022, -- 2405.01535 Prometheus 2: An Open Source Language Model Specialized in Evaluating
        31038, -- 2405.01886 Aloe: A Family of Fine-tuned Open Healthcare LLMs
        31303, -- 2405.09055 A safety realignment framework via subspace-oriented model fusion for
        31495, -- 2405.13053 MeteoRA: Multiple-tasks Embedded LoRA for Large Language Models
        31512, -- 2405.13432 Disperse-Then-Merge: Pushing the Limits of Instruction Tuning via Alig
        31578, -- 2405.14366 MiniCache: KV Cache Compression in Depth Dimension for Large Language
        31855, -- 2405.17472 FreezeAsGuard: Mitigating Illegal Adaptation of Diffusion Models via S
        31893, -- 2405.17931 Online Merging Optimizers for Boosting Rewards and Mitigating Tax in A
        32056, -- 2405.19950 Multimodal Lego: Model Merging and Fine-Tuning Across Topologies and M
        32527, -- 2406.05223 CorDA: Context-Oriented Decomposition Adaptation of Large Language Mod
        32690, -- 2406.07188 Merging Improves Self-Critique Against Jailbreak Attacks
        32732, -- 2406.07529 MAP: Low-compute Model Merging with Amortized Pareto Fronts via Quadra
        32846, -- 2406.08903 Delta-CoMe: Training-Free Delta-Compression with Mixed-Precision for L
        33098, -- 2406.11385 MetaGPT: Merging Large Language Models Using Model Exclusive Task Arit
        33194, -- 2406.12034 Self-MoE: Towards Compositional Large Language Models with Self-Specia
        33256, -- 2406.12585 Breaking the Ceiling of the LLM Community by Treating Token Generation
        33308, -- 2406.13175 Sparse High Rank Adapters
        33421, -- 2406.14563 Model Merging and Safety Alignment: One Bad Model Spoils the Bunch
        33463, -- 2406.14971 Domain Adaptation of Llama3-70B-Instruct through Continual Pre-Trainin
        33493, -- 2406.15479 Twin-Merging: Dynamic Integration of Modular Expertise in Model Mergin
        33597, -- 2406.16768 WARP: On the Benefits of Weight Averaged Rewarded Policies
        33694, -- 2406.17923 PAFT: A Parallel Training Paradigm for Effective LLM Fine-Tuning
        34053, -- 2407.02447 PLeaS -- Merging Models with Permutations and Least Squares
        34160, -- 2407.03994 Unlocking the Potential of Model Merging for Low-Resource Languages
        34315, -- 2407.06089 Merge, Ensemble, and Cooperate! A Survey on Collaborative Strategies i
        34509, -- 2407.08699 Mitigating Catastrophic Forgetting in Language Transfer via Model Merg
        34768, -- 2407.11895 OmniBind: Large-scale Omni Multimodal Representation via Binding Space
        35004, -- 2407.14962 Recent Advances in Generative AI and Large Language Models: Current St
        35007, -- 2407.15017 Knowledge Mechanisms in Large Language Models: A Survey and Perspectiv
        35588, -- 2408.03092 Extend Model Merging from Fine-Tuned to Pre-Trained Large Language Mod
        35844, -- 2408.07666 Model Merging in LLMs, MLLMs, and Beyond: Methods, Theories, Applicati
        35854, -- 2408.07990 FuseChat: Knowledge Fusion of Chat Models
        36314, -- 2408.15666 StyleRemix: Interpretable Authorship Obfuscation via Distillation and
        36333, -- 2408.15915 Leveraging Open Knowledge for Advancing Task Expertise in Large Langua
        36519, -- 2409.01659 Interpreting and Improving Large Language Models in Arithmetic Calcula
        36606, -- 2409.03274 Recent Advances in Attack and Defense Approaches of Large Language Mod
        36852, -- 2409.08846 FP-VEC: Fingerprinting Large Language Models via Efficient Vector Addi
        37412, -- 2409.18314 Realistic Evaluation of Model Merging for Compositional Generalization
        37637, -- 2410.01335 Layer Swapping for Zero-Shot Cross-Lingual Transfer in Large Language
        37656, -- 2410.01497 DLP-LoRA: Efficient Task-Specific LoRA Fusion with a Dynamic, Lightwei
        37669, -- 2410.01610 Upcycling Instruction Tuning from Dense to Mixture-of-Experts via Para
        37756, -- 2410.02396 Parameter Competition Balancing for Model Merging
        37885, -- 2410.03617 What Matters for Model Merging at Scale?
        37906, -- 2410.03782 DaWin: Training-free Dynamic Weight Interpolation for Robust Adaptatio
        38067, -- 2410.05770 Efficient Few-shot Learning for Multi-label Classification of Scientif
        38218, -- 2410.07571 How Does Vision-Language Adaptation Impact the Safety of Vision Langua
        38454, -- 2410.10739 Balancing Continuous Pre-Training and Instruction Fine-Tuning: Optimiz
        38465, -- 2410.10801 Mix Data or Merge Models? Optimizing for Diverse Multi-Task Learning
        38618, -- 2410.12613 Exploring Model Kinship for Merging Large Language Models
        38704, -- 2410.13394 Cross-Lingual Auto Evaluation for Assessing Multilingual LLMs
        38727, -- 2410.13699 Unconstrained Model Merging for Enhanced LLM Reasoning
        38728, -- 2410.13708 On the Role of Attention Heads in Large Language Model Safety
        38765, -- 2410.13910 Mitigating the Backdoor Effect for Multi-Task Model Merging via Safety
        38833, -- 2410.14735 Agent Skill Acquisition for Large Language Models via CycleQD
        38890, -- 2410.15633 GATEAU: Selecting Influential Samples for Long Context Alignment
        39002, -- 2410.17146 LiNeS: Post-training Layer Scaling Prevents Forgetting and Enhances Mo
        39499, -- 2411.00406 MoD: A Distribution-Based Approach for Merging Large Language Models
        41139, -- 2412.05148 LoRA.rar: Learning to Merge LoRAs via Hypernetworks for Subject-Style
        41554, -- 2412.10416 SUPERMERGE: An Approach For Gradient-Based Model Merging
        41561, -- 2412.10493 SafetyDPO: Scalable Safety Alignment for Text-to-Image Generation
        41594, -- 2412.11041 Separate the Wheat from the Chaff: A Post-Hoc Approach to Safety Re-Al
        41646, -- 2412.11704 Vocabulary Expansion of Chat Models with Unlabeled Target Language Dat
        41977, -- 2412.15646 CustomTTT: Motion and Appearance Customized Video Generation via Test-
        42208, -- 2412.19098 Tint Your Models Task-wise for Improved Multi-task Model Merging
        42226, -- 2412.19512 Safeguard Fine-Tuned LLMs Through Pre- and Post-Tuning Model Merging
        42411, -- 2501.01230 Modeling Multi-Task Model Merging as Adaptive Projective Gradient Desc
        43421, -- 2501.18512 Streaming DiLoCo with overlapping communication: Towards a Distributed
        43535, -- 2502.00997 MergeME: Model Merging Techniques for Homogeneous and Heterogeneous Mo
        43651, -- 2502.02421 Activation-Informed Merging of Large Language Models
        43832, -- 2502.04959 No Task Left Behind: Isotropic Model Merging with Common and Task-Spec
        43882, -- 2502.05633 Mol-MoE: Training Preference-Guided Routers for Molecule Generation
        44136, -- 2502.09056 Adapting Language-Specific LLMs to a Reasoning Model in One Day via Mo
        44210, -- 2502.10339 STAR: Spectral Truncation and Rescale for Model Merging
        44220, -- 2502.10436 MERGE$^3$: Efficient Evolutionary Merging on Consumer-grade GPUs
        44229, -- 2502.10525 Towards Watermarking of Open-Source LLMs
        44242, -- 2502.10698 Superpose Singular Features for Model Merging
        44246, -- 2502.10743 1bit-Merging: Dynamic Quantized Merging for Large Language Models
        44247, -- 2502.10749 LoRE-Merging: Exploring Low-Rank Estimation For Large Language Model M
        44300, -- 2502.11191 Primus: A Pioneering Collection of Open-Source Datasets for Cybersecur
        44305, -- 2502.11244 Soteria: Language-Specific Functional Parameter Steering for Multiling
        44435, -- 2502.12217 Optimal Brain Iterative Merging: Mitigating Interference in LLM Mergin
        44443, -- 2502.12420 Sens-Merging: Sensitivity-Guided Parameter Balancing for Merging Large
        44763, -- 2502.15483 MoMa: A Modular Deep Learning Framework for Material Property Predicti
        44866, -- 2502.16770 LED-Merging: Mitigating Safety-Utility Conflicts in Model Merging with
        44915, -- 2502.17159 Parameter Efficient Merging for Multimodal Large Language Models with
        45289, -- 2503.00948 Extrapolating and Decoupling Image-to-Video Generation Models: Motion
        45303, -- 2503.01155 Nature-Inspired Population-Based Evolution of Large Language Models
        45332, -- 2503.01496 Liger: Linearizing Large Language Models to Gated Recurrent Structures
        45371, -- 2503.01874 CABS: Conflict-Aware and Balanced Sparsification for Enhancing Model M
        45547, -- 2503.04543 Keeping Yourself is Important in Downstream Tuning Multimodal Large La
        45737, -- 2503.06921 Task Vector Quantization for Memory-Efficient Model Merging
        45973, -- 2503.09501 ReMA: Learning to Meta-think for LLMs with Multi-Agent Reinforcement L
        46766, -- 2503.20110 Efficient Model Development through Fine-tuning Transfer
        46799, -- 2503.20641 Unlocking Efficient Long-to-Short LLM Reasoning with Model Merging
        46825, -- 2503.21088 ZJUKLAB at SemEval-2025 Task 4: Unlearning via Model Merging
        46839, -- 2503.21272 Reinforced Model Merging
        46913, -- 2503.22178 AdaRank: Adaptive Rank Pruning for Enhanced Model Merging
        47032, -- 2503.23733 AdaMMS: Model Merging for Heterogeneous Multimodal Large Language Mode
        47408, -- 2504.05747 SEA-LION: Southeast Asian Languages in One Network
        47485, -- 2504.07448 LoRI: Reducing Cross-Task Interference in Multi-Task Low-Rank Adaptati
        47995, -- 2504.15133 EasyEdit2: An Easy-to-use Steering Framework for Editing Large Languag
        48271, -- 2504.21659 Ada-R1: Hybrid-CoT via Bi-Level Adaptive Reasoning Optimization
        48400, -- 2505.02486 SEFE: Superficial and Essential Forgetting Eliminator for Multimodal C
        48539, -- 2505.05464 Bring Reason to Vision: Understanding Perception and Reasoning through
        48797, -- 2505.10717 A Modular Approach for Clinical SLMs Driven by Synthetic Data with Pre
        48865, -- 2505.11427 Mergenetic: a Simple Evolutionary Model Merging Library
        48924, -- 2505.12082 Model Merging in Pre-training of Large Language Models
        49102, -- 2505.13878 InfiFPO: Implicit Model Fusion via Preference Optimization in Large La
        49370, -- 2505.16151 Training-Free Reasoning and Reflection in MLLMs
        49524, -- 2505.17496 Analyzing Mitigation Strategies for Catastrophic Forgetting in End-to-
        49534, -- 2505.17592 AstroMLab 4: Benchmark-Topping Performance in Astronomy Q&A with a 70B
        49619, -- 2505.18502 Knowledge Grafting of Large Language Models
        49775, -- 2505.19797 The Avengers: A Simple Recipe for Uniting Smaller Language Models to C
        50386, -- 2506.01482 Automatic Stage Lighting Control: Is it a Rule-Driven Process or Gener
        50908, -- 2506.09093 Merging Smarter, Generalizing Better: Enhancing Model Merging on OOD D
        51030, -- 2506.10822 ReCUT: Balancing Reasoning Length and Accuracy in LLMs via Stepwise Tr
        51462, -- 2506.20480 GPTailor: Large Language Model Pruning Through Layer Cutting and Stitc
        51501, -- 2506.21260 DuET: Dual Incremental Object Detection via Exemplar-Free Task Arithme
        51561, -- 2506.22813 Selecting and Merging: Towards Adaptable and Scalable Named Entity Rec
        52181, -- 2508.02120 Don't Overthink It: A Survey of Efficient R1-style Large Reasoning Mod
        52382, -- 2508.11032 MedSAMix: A Training-Free Model Merging Approach for Medical Image Seg
        52607, -- 2509.01363 Reasoning Vectors: Transferring Chain-of-Thought Capabilities via Task
        52623, -- 2509.02108 DivMerge: A divergence-based model merging method for multi-tasking
        52916, -- 2509.17786 Accurate and Efficient Low-Rank Model Merging in Core Space
        53437, -- 2510.05608 A Goal Without a Plan Is Just a Wish: Efficient and Effective Global P
        53570, -- 2510.10977 Revisiting Model Interpolation for Efficient Reasoning
        53588, -- 2510.09913 Don't Throw Away Your Pretrained Model
        53760, -- 2510.15050 Directional Reasoning Injection for Fine-Tuning MLLMs
        53819, -- 2510.20479 RECALL: REpresentation-aligned Catastrophic-forgetting ALLeviation via
        53821, -- 2510.21223 Model Merging with Functional Dual Anchors
        54016, -- 2511.00062 World Simulation with Video Foundation Models for Physical AI
        54216, -- 2511.13254 Souper-Model: How Simple Arithmetic Unlocks State-of-the-Art LLM Perfo
        54590, -- 2512.04844 Mitigating Catastrophic Forgetting in Target Language Adaptation of LL
        54956, -- 2512.20182 FaithLens: Detecting and Explaining Faithfulness Hallucination
        54988, -- 2512.13043 GTR-Turbo: Merged Checkpoint is Secretly a Free Teacher for Agentic VL
        55159, -- 2601.05106 Token-Level LLM Collaboration via FusionRoute
        55420, -- 2601.13572 Behavior Knowledge Merge in Reinforced Agentic Models
        55730, -- 2602.00747 Decouple Searching from Training: Scaling Data Mixing via Model Mergin
        56057, -- 2602.09021 χ_{0}: Resource-Aware Robust Manipulation via Taming Distributional In
        57112, -- 2604.00007 Dynin-Omni: Omnimodal Unified Large Diffusion Language Model
        57121, -- 2603.28858 OptiMer: Optimal Distribution Vector Merging Is Better than Data Mixin
        57431, -- 2604.11446 Low-rank Optimization Trajectories Modeling for LLM RLVR Acceleration
        57588, -- 2604.16826 Crowded in B-Space: Calibrating Shared Directions for LoRA Merging
        57891, -- 2512.09972 AP-BMM: Approximating Capability-Efficiency Pareto Sets of LLMs via As
        58798, -- 2511.21437 A Systematic Study of In-the-Wild Model Merging for Large Language Mod
        58980, -- 2603.22755 KALAVAI: Predicting When Independent Specialist Fusion Works -- A Quan
        58986, -- 2603.23408 GeoSANE: Learning Geospatial Representations from Models, Not Data
        59780, -- 2603.06242 DC-Merge: Improving Model Merging with Directional Consistency
        59858, -- 2603.04972 Functionality-Oriented LLM Merging on the Fisher--Rao Manifold
        60424, -- 2602.19058 Do LLMs and VLMs Share Neurons for Inference? Evidence and Mechanisms
        60484, -- 2603.06610 CapTrack: Multifaceted Evaluation of Forgetting in LLM Post-Training
        60731, -- 2602.12566 To Mix or To Merge: Toward Multi-Domain Reinforcement Learning for Lar
        61083, -- 2602.06665 Not All Layers Need Tuning: Selective Layer Restoration Recovers Diver
        61197, -- 2602.05943 Orthogonal Model Merging
        61236, -- 2602.04937 Linear Model Merging Unlocks Simple and Scalable Multimodal Data Mixtu
        61624, -- 2602.00585 Exploring Information Seeking Agent Consolidation
        61720, -- 2601.22620 Layer-wise Swapping for Generalizable Multilingual Safety
        62070, -- 2601.17858 MergeMix: Optimizing Mid-Training Data Mixtures via Learnable Model Me
        62447, -- 2601.10804 BYOL: Bring Your Own Language Into LLMs
        62658, -- 2601.07309 ARM: Role-Conditioned Neuron Transplantation for Training-Free General
        62696, -- 2601.06672 Will it Merge? On The Causes of Model Mergeability
        62774, -- 2601.05062 Compositional Steering of Large Language Models with Steering Tokens
        63617, -- 2512.15233 Null-LoRA: Low-Rank Adaptation on Null Space
        64096, -- 2512.05117 The Universal Weight Subspace Hypothesis
        64633, -- 2511.18810 MergeVLA: Cross-Skill Model Merging Toward a Generalist Vision-Languag
        66166, -- 2510.17426 Navigating the Alignment-Calibration Trade-off: A Pareto-Superior Fron
        66346, -- 2510.14163 Towards Reversible Model Merging For Low-rank Weights
        66351, -- 2510.13999 REAP the Experts: Why Pruning Prevails for One-Shot MoE compression
        66403, -- 2510.13537 K-Merge: Online Continual Merging of Adapters for On-device Large Lang
        66711, -- 2510.08396 FlyLoRA: Boosting Task Decoupling and Parameter Efficiency via Implici
        67360, -- 2509.25712 Expert Merging: Model Merging with Unsupervised Expert Alignment and I
        67793, -- 2509.21164 Mixture of Thoughts: Learning to Aggregate What Experts Think, Not Jus
        67951, -- 2509.18883 LongCat-Flash-Thinking Technical Report
        68323, -- 2509.12951 Black-box Model Merging for Language-Model-as-a-Service with Massive M
        68408, -- 2509.11414 Continually Adding New Languages to Multilingual Language Models
        68424, -- 2509.11167 Harnessing Optimization Dynamics for Curvature-Informed Model Merging
        68866, -- 2509.01548 Model Unmerging: Making Your Models Unmergeable for Secure Model Shari
        69131, -- 2508.19353 Efficient Multi-Source Knowledge Transfer by Model Merging
        69329, -- 2508.16204 Competition and Attraction Improve Model Fusion
        69337, -- 2508.16082 On Task Vectors and Gradients
        69618, -- 2508.11442 CoDiEmb: A Collaborative yet Distinct Framework for Unified Representa
        69906, -- 2508.07414 Grounding Multilingual Multimodal LLMs With Cultural Knowledge
        70136, -- 2508.04153 ICM-Fusion: In-Context Meta-Optimized LoRA Fusion for Multi-Task Adapt
        70156, -- 2508.04037 SEA: Self-Evolution Agent with Step-wise Reward for Computer Use
        70224, -- 2508.03140 RCP-Merging: Merging Long Chain-of-Thought Models with Domain-Specific
        70226, -- 2508.03121 RegMean++: Enhancing Effectiveness and Generalization of Regression Me
        71184, -- 2507.09662 Towards Concise and Adaptive Thinking in Large Reasoning Models: A Sur
        72272, -- 2506.15721 Bohdi: Heterogeneous LLM Fusion with Automatic Data Exploration
        72305, -- 2506.03800 STELLA: Towards Protein Function Prediction with Multimodal LLMs Integ
        72472, -- 2506.14794 Assembly of Experts: Linear-time construction of the Chimera LLM varia
        72556, -- 2505.23117 Decom-Renorm-Merge: Model Merging on the Right Space Improves Multitas
        72881, -- 2505.15875 Decouple and Orthogonalize: A Data-Free Framework for LoRA Merging
        72937, -- 2505.14136 Local Mixtures of Experts: Essentially Free Test-Time Training via Mod
        73051, -- 2505.10833 MergeBench: A Benchmark for Merging Domain-Specialized LLMs
        73467, -- 2504.13237 ImPart: Importance-Aware Delta-Sparsification for Improved Model Compr
        74316, -- 2503.02103 Superficial Self-Improved Reasoners Benefit from Model Merging
        75679, -- 2411.18607 Task Arithmetic Through The Lens Of One-Shot Federated Learning
        75690, -- 2412.00081 Task Singular Vectors: Reducing Task Interference in Model Merging
        76031, -- 2410.13025 LoRA Soups: Merging LoRAs for Practical Skill Composition Tasks
        76068, -- 2410.09982 Self-Data Distillation for Recovering Quality in Pruned Large Language
        76267, -- 2405.17461 EMR-Merging: Tuning-Free High-Performance Model Merging
        76524, -- 2408.13656 Localize-and-Stitch: Efficient Model Merging via Sparse Task Arithmeti
        76865, -- 2407.00487 It's Morphing Time: Unleashing the Potential of Multiple LLMs via Mult
        83135, -- 2605.13030 FeatCal: Feature Calibration for Post-Merging Models
        83169, -- 2605.14386 Darwin Family: MRI-Trust-Weighted Evolutionary Merging for Training-Fr
        83402, -- 2605.16882 E-PMQ: Expert-Guided Post-Merge Quantization with Merged-Weight Anchor
        84161, -- 2511.11851 Defending Unauthorized Model Merging via Dual-Stage Weight Protection
        84572, -- 2602.20208 Model Merging in the Essential Subspace
        84721, -- 2603.02945 ACE-Merging: Data-Free Model Merging with Adaptive Covariance Estimati
        84737, -- 2603.03920 BD-Merging: Bias-Aware Dynamic Model Merging with Evidence-Guided Cont
        84767, -- 2603.05768 Bridging Domains through Subspace-Aware Model Merging
        85003, -- 2603.20470 DiffGraph: An Automated Agent-driven Model Merging Framework for In-th
        85147, -- 2603.26299 Preference-Aligned LoRA Merging: Preserving Subspace Coverage and Addr
        85148, -- 2603.26317 Label-Free Cross-Task LoRA Merging with Null-Space Compression
        85755, -- 2510.11268 Exploring and Leveraging Class Vectors for Classifier Editing
        85773, -- 2505.11883 MINGLE: Mixtures of Null-Space Gated Low-Rank Experts for Test-Time Co
        85896, -- 2505.14009 Activation-Guided Consensus Merging for Large Language Models
        86036, -- 2509.18208 Variational Task Vector Composition
        86158, -- 2505.22860 Permissioned LLMs: Enforcing Access Control in Large Language Models
        86493, -- 2510.14387 Can MLLMs Absorb Math Reasoning Abilities from LLMs as Free Lunch?
        86519, -- 2505.13515 LoRASuite: Efficient LoRA Adaptation Across Large Language Model Upgra
        87068, -- 2505.22389 Train with Perturbation, Infer after Merging: A Two-Stage Framework fo
        87151, -- 2502.04510 Heterogeneous Swarms: Jointly Optimizing Model Roles and Weights for M
        87247, -- 2409.18893 HM3: Hierarchical Multi-Objective Model Merging for Pretrained Models
        87450, -- 2502.11806 Exploring Translation Mechanism of Large Language Models
        87728, -- 2503.07661 Disrupting Model Merging: A Parameter-Level Defense Without Sacrificin
        88943, -- 2502.05784 Propagation of Chaos for Mean-Field Langevin Dynamics and its Applicat
        89257, -- 2410.11163 Model Swarms: Collaborative Search to Adapt LLM Experts via Swarm Inte
        89694, -- 2502.12706 Scalable Model Merging with Progressive Layer-wise Distillation
        89866, -- 2503.08099 Whoever Started the interference Should End It: Guiding Data-Free Mode
        90488, -- 2503.16843 LoRASculpt: Sculpting LoRA for Harmonizing General and Specialized Kno
        90719, -- 2503.01359 DeRS: Towards Extremely Efficient Upcycled Mixture-of-Experts Models
        90950, -- 2412.06712 How to Merge Your Multimodal Models Over Time?
        91125, -- 2410.19735 Model merging with SVD to tie the Knots
        91381, -- 2410.09343 ELICIT: LLM Augmentation Via External In-context Capability
        91664, -- 2502.18821 CAMEx: Curvature-aware Merging of Experts
        92472, -- 2606.01717 Decentralized Instruction Tuning: Conflict-Aware Splitting and Weight
        92559, -- 2605.29489 Access Sets Matter: Budgeting Expert Reads for Scalable Weight-Space M
        92841, -- 2504.05342 MASS: MoErging through Adaptive Subspace Selection
        93204, -- 2602.22538 RAIN-Merging: A Gradient-Free Method to Enhance Instruction Following
        93420, -- 2603.01526 Scalable Multi-Task Low-Rank Model Adaptation
        93430, -- 2505.23209 Navigating the Accuracy-Size Trade-Off with Flexible Model Merging
        93460, -- 2504.05902 Defending against Backdoor Attacks via Module Switching
        93745, -- 2502.00241 Mordal: Automated Pretrained Model Selection for Vision Language Model
        93932, -- 2503.10705 Enhanced Continual Learning of Vision-Language Models with Model Fusio
        94180, -- 2510.16138 Expert Merging in Sparse Mixture of Experts with Nash Bargaining
        94286, -- 2502.07274 Forget Forgetting: Continual Learning in a World of Abundant Memory
        94561, -- 2511.07970 Continual Unlearning for Text-to-Image Diffusion Models: A Regularizat
        94791, -- 2601.10497 MergeTune: Continued Fine-Tuning of Vision-Language Models
        94919, -- 2512.04695 Trinity: An Evolved LLM Coordinator
        94926, -- 2509.21413 Null-Space Filtering for Data-Free Continual Model Merging: Preserving
        95096, -- 2606.05846 Towards Truly Multilingual ASR: Generalizing Code-Switching ASR to Uns
        98773, -- 2606.24346 PETRA: Transforming Web Text for Petroleum-Engineering Domain Adaptati
        98887, -- 2606.26080 Neglected Free Lunch from Post-training: Progress Advantage for LLM Ag
        99021, -- 2606.30406 MOPD: Multi-Teacher On-Policy Distillation for Capability Integration
        99039, -- 2607.00666 Domain Arithmetic: One-Shot VLA Adaptation under Environmental Shifts
        99078, -- 2607.02291 Optimizing Visual Generative Models via Distribution-wise Rewards
        99099, -- 2607.01686 WARP: Weight-Space Analysis for Recovering Training Data Portfolios
        99141, -- 2601.21187 FRISM: Fine-Grained Reasoning Injection via Subspace-Level Model Mergi
        99190, -- 2602.05536 When Shared Knowledge Hurts: Spectral Over-Accumulation in Model Mergi
        99314, -- 2605.29295 EvoGM: Learning to Merge LLMs via Evolutionary Generative Optimization
        99736, -- 2606.10617 SSR-Merge: Subspace Signal Routing for Training-Free LoRA Merging in D
        99820, -- 2605.26484 Extra-Merge: Tracing the Rank-1 Subspace of Model Merging in Language
        99824, -- 2606.25761 Bridging Spherical Black-Box Optimizers
        100230, -- 2601.22285 Demystifying Mergeability: Interpretable Properties to Predict Model M
        100755, -- 2606.16501 Post-Hoc Merging is Not Enough: Many-Shot Model Merging with Loss-Gap
        100831, -- 2606.03723 Compress then Merge: From Multiple LoRAs into One Low-Rank Adapter
        100910, -- 2602.04509 Model-Dowser: Data-Free Importance Probing to Mitigate Catastrophic Fo
        101126, -- 2605.28577 Continual Model Routing in Evolving Model Hubs
        101280, -- 2603.01097 Understanding LoRA as Knowledge Memory: An Empirical Analysis
        101546, -- 2601.21898 Making Models Unmergeable via Scaling-Sensitive Loss Landscape
        101661, -- 2606.00511 Saliency-Aware Model Merging
        101985, -- 2506.14126 From Memorization to Parameter Interference: How Overtraining Experts
        102799, -- 2410.04524 Toward Secure Tuning: Mitigating Security Risks from Instruction Fine-
        102895, -- 2605.01256 GIFT: Guided Fine-Tuning and Transfer for Enhancing Instruction-Tuned
        102951, -- 2604.15294 How Do LLMs and VLMs Understand Viewpoint Rotation Without Vision? An
        103066, -- 2602.05176 Among Us: Measuring and Mitigating Malicious Contributions in Model Co
        103092, -- 2502.04506 When One LLM Drools, Multi-LLM Collaboration Rules
        103102, -- 2604.19015 FedProxy: Federated Fine-Tuning of LLMs via Proxy SLMs and Heterogenei
        103147, -- 2604.14808 Modeling LLM Unlearning as an Asymmetric Two-Task Learning Problem
        103321, -- 2605.18083 A Data-Efficient Path to Multilingual LLMs: Language Expansion via Pos
        103539, -- 2604.17753 Evolutionary Negative Module Pruning for Better LoRA Merging
        103714, -- 2505.21226 Why Do More Experts Fail? A Theoretical Analysis of Model Merging
        103758, -- 2601.05560 ReasonAny: Incorporating Reasoning Capability to Any Model via Simple
        104051, -- 2607.03065 Spectral Rewiring for Exploration, Purification, and Model Merging
        104536, -- 2605.20296 Spectral Unforgetting: Post-Hoc Recovery of Damaged Capabilities Witho
        105401, -- 2503.01164 Med-LEGO: Editing and Adapting toward Generalist Medical Image Diagnos
        105646, -- 2503.07799 Self-supervised Normality Learning and Divergence Vector-guided Model
        106255, -- 2604.01329 Model Merging via Data-Free Covariance Estimation
        106321, -- 2604.06465 Multi-objective Evolutionary Merging Enables Efficient Reasoning Model
        107228, -- 2511.10712 Do Not Merge My Model! Safeguarding Open-Source LLMs Against Unauthori
        108383, -- 2602.08564 M-Loss: Quantifying Model Merging Compatibility with Limited Unlabeled
        108473, -- 2511.10943 From Parameter to Representation: A Closed-Form Approach for Controlla
        108939, -- 2608.06216 Continual Learning in Transition
        108974, -- 2608.03573 SFT Conflicts, RL Coexists: A Theoretical and Empirical Analysis of Mu
        109088, -- 2608.08627 UniMoMo: Expert Merging-Based MoE Acceleration for Large Recommendatio
        109530, -- 2608.20281 Inject, Align, Recover: Staged Post-Training for Retrieval-Free Docume
        109765, -- 2608.19098 Open-MOPD: Diagnosing and Fixing Capability Imbalance in Multi-Teacher
        110102, -- 2502.16094 Merger-as-a-Stealer: Stealing Targeted PII from Aligned LLMs with Mode
        110143, -- 2509.09703 CTCC: A Robust and Stealthy Fingerprinting Framework for Large Languag
        110145, -- 2509.03058 EverTracer: Hunting Stolen Large Language Models via Stealthy and Robu
        110347, -- 2503.07663 Merge then Realign: Simple and Effective Modality-Incremental Continua
        110437, -- 2503.05320 To See a World in a Spark of Neuron: Disentangling Multi-Task Interfer
        110499, -- 2410.07825 Extracting and Combining Abilities For Building Multi-lingual Ability-
        110676, -- 2509.17688 TASO: Task-Aligned Sparse Optimization for Parameter-Efficient Model A
        110733, -- 2505.18548 Composable Cross-prompt Essay Scoring by Merging Models
        110743, -- 2509.19727 Personality Vector: Modulating Personality of Large Language Models by
        110817, -- 2507.17706 HydraOpt: Navigating the Efficiency-Performance Trade-off of Adapter M
        110861, -- 2507.16083 Efficient Compositional Multi-tasking for On-device Large Language Mod
        110938, -- 2505.21963 LaMDAgent: An Autonomous Framework for Post-Training Pipeline Optimiza
        111085, -- 2503.18008 Personalized Language Models via Privacy-Preserving Evolutionary Model
        118146, -- 2606.24963 Curvature-Guided Mixing for MLLM Adaptation
        118147, -- 2607.19971 Unified Prediction and Planning via Conflict-Aware Disjoint Parameter
        118166, -- 2606.22589 Training-Free Task Classification for Multi-Task Model Merging
        118170, -- 2512.01461 Stay Unique, Stay Efficient: Preserving Model Personality in Multi-Tas
        118180, -- 2606.26902 Learning to Recover Task Experts from a Multi-Task Merged Model
        118210, -- 2606.30360 On the Vulnerability of Parameter-Level Defenses to Model Merging
        121951, -- 2609.14708 Lightning Weave: Improving the Accuracy-Efficiency Frontier of Reasoni
        122376, -- 2609.32821 Routing Drift Alone Does Not Diagnose Failure in Merged MoE LLMs
        122379, -- 2609.33437 SMAT: Simple and Efficient Merge-Aware Training
        122443, -- 2609.22237 Not All Ranks Are Equal: Budget-Aware LoRA Merging Across Tasks
        122731, -- 2609.39420 QuantCode Model: Specializing Language Models for Executable Algorithm
        122874, -- 2610.10429 SGF+: Decoupling Gradient Flows for Autoregressive Video Generation
        123553, -- 2610.21055 Athanor: An Agent-Native System for Autonomous Post-Training Research
        124549, -- 2607.20435 Making Open-Source Text LLM Watermarks Durable Against Merging
        124824, -- 2508.21421 Rethinking Layer-wise Model Merging through Chain of Merges
        125035, -- 2607.03011 Can Model Merging Improve Aggregation in DiLoCo?
        126023, -- 2605.14084 CRANE: Constrained Reasoning Injection for Code Agents via Nullspace E
        126406, -- 2609.09054 Training-Free Task Vectors for LLM Behavioral Control
        126595, -- 2604.05502 AttnDiff: Attention-based Differential Fingerprinting for Large Langua
        126765, -- 2610.14558 PGSB: Pretrained-Guided Shared Basis for LoRA Model Merging
        127316, -- 2605.12960 DiM$^3$: Bridging Multilingual and Multimodal Models via Direction- an
        128102, -- 2605.18904 Dynamic Model Merging Made Slim
        128230, -- 2609.32332 When the Merge Coefficient Stops Mattering: Proximity Regularized Merg
        128276, -- 2605.12384 Scalable Token-Level Hallucination Detection in Large Language Models
        128667, -- 2610.01238 Mixture-Trained Merging for Unified Multi-Objective Models
        128703, -- 2606.00357 From “Weak” Signals to Strong Models: Preference Delta Aggregation wit
        129214, -- 2605.31494 Consolidating Rewarded Perturbations for LLM Post-Training
        129597, -- 2604.20985 Differentially Private Model Merging
        130022, -- 2602.18658 Communication-Efficient Personalized Adaptation via Federated-Local Mo
        130267, -- 2605.09879 M2A: Synergizing Mathematical and Agentic Reasoning in Large Language
        130800, -- 2604.03420 Zero-Shot Quantization via Weight-Space Arithmetic
        131879, -- 2611.05609 On the Generalization Limitation of On-Policy Distillation for Post-RL
        131995, -- 2611.03953 P^2-MOPD: Accelerating Multi-Teacher On-Policy Distillation via Parame
        132071  -- 2611.09634 Steerable Multi-Objective Group-Relative Preference Optimization with
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
