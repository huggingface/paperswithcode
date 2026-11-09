-- Add a Deep Learning domain with PyTorch, JAX, and TensorFlow to the framework catalog.
-- Production chat users looked these up with pwc_get_framework (2026-10-31 and
-- 2026-11-08 audits); the catalog only had task-specific libraries built on them.

BEGIN;

INSERT INTO framework_domains (slug, name, description, display_order)
VALUES (
    'deep-learning',
    'Deep Learning',
    'General-purpose deep-learning frameworks for defining, training, and deploying neural networks, on which most other libraries are built.',
    8
)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    display_order = EXCLUDED.display_order,
    updated_at = now();

INSERT INTO framework_categories (domain_id, slug, name, description, display_order)
SELECT domain.id,
       'deep-learning-frameworks',
       'Deep Learning Frameworks',
       'Core libraries for tensors, automatic differentiation, and accelerated neural-network training.',
       0
FROM framework_domains domain
WHERE domain.slug = 'deep-learning'
ON CONFLICT (domain_id, slug) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    display_order = EXCLUDED.display_order,
    updated_at = now();

INSERT INTO repositories (url, owner, name, num_stars, source)
VALUES
    ('https://github.com/pytorch/pytorch', 'pytorch', 'pytorch', 0, 'framework_catalog'),
    ('https://github.com/jax-ml/jax', 'jax-ml', 'jax', 0, 'framework_catalog'),
    ('https://github.com/tensorflow/tensorflow', 'tensorflow', 'tensorflow', 0, 'framework_catalog')
ON CONFLICT (url) DO NOTHING;

WITH framework_data(slug, name, organization_name, repo_url, arxiv_id, description, when_to_use, docs_url, display_order, abstract_linking) AS (
    VALUES
        (
            'pytorch',
            'PyTorch',
            'PyTorch Foundation',
            'https://github.com/pytorch/pytorch',
            '1912.01703',
            'An open-source deep-learning framework with eager tensor execution, automatic differentiation, GPU acceleration, and torch.compile for graph-level optimization. Most research code and many of the libraries in this catalog are built on it.',
            'Use PyTorch to write and train custom models, reproduce research code, or build on its ecosystem, including Transformers, timm, PyTorch Geometric, and Lightning.',
            'https://docs.pytorch.org/docs/stable/index.html',
            0,
            'always'
        ),
        (
            'jax',
            'JAX',
            'Google',
            'https://github.com/jax-ml/jax',
            NULL,
            'A Python library for accelerator-oriented array computation with composable function transformations: automatic differentiation (grad), JIT compilation through XLA (jit), vectorization (vmap), and parallelization across devices.',
            'Use JAX for research that needs custom gradients, functional programs, or large-scale TPU/GPU training, typically with Flax, Optax, or MaxText on top.',
            'https://docs.jax.dev/en/latest/',
            1,
            'judge'
        ),
        (
            'tensorflow',
            'TensorFlow',
            'Google',
            'https://github.com/tensorflow/tensorflow',
            '1603.04467',
            'An open-source machine-learning platform with the Keras high-level API, XLA compilation, distributed training, and deployment tooling for servers (TF Serving), mobile and edge devices (LiteRT, formerly TensorFlow Lite), and browsers (TensorFlow.js).',
            'Use TensorFlow to maintain or reproduce existing TensorFlow/Keras code, or when you need its production deployment stack for mobile, edge, or browser targets.',
            'https://www.tensorflow.org/api_docs',
            2,
            'always'
        )
)
INSERT INTO frameworks (
    category_id, repository_id, introducing_paper_id, slug, name, organization_name,
    description, when_to_use, docs_url, display_order, abstract_linking
)
SELECT
    category.id,
    repository.id,
    (SELECT paper.id FROM papers paper
     WHERE paper.arxiv_id = framework_data.arxiv_id
     ORDER BY paper.is_latest_version DESC, paper.id DESC LIMIT 1),
    framework_data.slug,
    framework_data.name,
    framework_data.organization_name,
    framework_data.description,
    framework_data.when_to_use,
    framework_data.docs_url,
    framework_data.display_order,
    framework_data.abstract_linking
FROM framework_data
JOIN framework_categories category ON category.slug = 'deep-learning-frameworks'
JOIN repositories repository ON repository.url = framework_data.repo_url
ON CONFLICT (slug) DO UPDATE SET
    category_id = EXCLUDED.category_id,
    repository_id = EXCLUDED.repository_id,
    introducing_paper_id = EXCLUDED.introducing_paper_id,
    name = EXCLUDED.name,
    organization_name = EXCLUDED.organization_name,
    description = EXCLUDED.description,
    when_to_use = EXCLUDED.when_to_use,
    docs_url = EXCLUDED.docs_url,
    display_order = EXCLUDED.display_order,
    abstract_linking = EXCLUDED.abstract_linking,
    updated_at = now();

INSERT INTO framework_platforms (framework_id, platform)
SELECT framework.id, platform.name
FROM frameworks framework
CROSS JOIN (VALUES ('gpu'), ('cpu'), ('apple')) AS platform(name)
WHERE framework.slug IN ('pytorch', 'jax', 'tensorflow')
ON CONFLICT DO NOTHING;

COMMIT;
