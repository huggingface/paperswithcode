"""Reviewed map from OpenAlex institutions to Papers With Code organizations.

Paper affiliations from OpenAlex are linked to an organization only through
this map, by OpenAlex institution ID, never by name, so look-alike or squatted
organization rows cannot attract links. Each institution maps to one canonical
organization row: the institution-level row with the most links when several
exist. Parent and child institutions stay separate (Google DeepMind is not
Google). A slug not yet in the catalog is created under ``name``.

The list covers institutions with at least 90 catalog papers since 2025 in
OpenAlex, plus the companies the catalog already features.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OpenAlexInstitution:
    openalex_id: str
    slug: str
    name: str


OPENALEX_INSTITUTIONS: tuple[OpenAlexInstitution, ...] = (
    # Universities and research institutes.
    OpenAlexInstitution("I99065089", "tsinghua", "Tsinghua University"),
    OpenAlexInstitution(
        "I4405263052", "tsinghua", "Tsinghua Shenzhen International Graduate School"
    ),
    OpenAlexInstitution("I20231570", "pekingu", "Peking University"),
    OpenAlexInstitution("I183067930", "sjtu", "Shanghai Jiao Tong University"),
    OpenAlexInstitution("I76130692", "zju", "Zhejiang University"),
    OpenAlexInstitution(
        "I19820366", "chinese-academy-of-sciences", "Chinese Academy of Sciences"
    ),
    OpenAlexInstitution(
        "I165932596",
        "nationaluniversityofsingapore",
        "National University of Singapore",
    ),
    OpenAlexInstitution(
        "I172675005",
        "nanyangtechnologicaluniversity",
        "Nanyang Technological University",
    ),
    OpenAlexInstitution("I74973139", "carnegiemellonu", "Carnegie Mellon University"),
    OpenAlexInstitution("I24943067", "fudan-university", "Fudan University"),
    OpenAlexInstitution(
        "I177725633", "cuhk-cse", "The Chinese University of Hong Kong"
    ),
    OpenAlexInstitution(
        "I200769079", "hkust", "Hong Kong University of Science and Technology"
    ),
    OpenAlexInstitution("I97018004", "stanforduniversity", "Stanford University"),
    OpenAlexInstitution(
        "I126520041",
        "ustc",
        "University of Science and Technology of China",
    ),
    OpenAlexInstitution(
        "I4210165038", "ucas", "University of Chinese Academy of Sciences"
    ),
    OpenAlexInstitution(
        "I157725225", "illinois", "University of Illinois Urbana-Champaign"
    ),
    OpenAlexInstitution(
        "I4391012619", "shanghaiailab", "Shanghai Artificial Intelligence Laboratory"
    ),
    OpenAlexInstitution("I889458895", "hkuhk", "The University of Hong Kong"),
    OpenAlexInstitution("I63966007", "mit", "Massachusetts Institute of Technology"),
    OpenAlexInstitution("I95457486", "berkeley", "University of California, Berkeley"),
    OpenAlexInstitution("I881766915", "nanjinguniv", "Nanjing University"),
    OpenAlexInstitution(
        "I157485424", "kaist-ai", "Korea Advanced Institute of Science and Technology"
    ),
    OpenAlexInstitution(
        "I4210112150", "casia", "Institute of Automation, Chinese Academy of Sciences"
    ),
    OpenAlexInstitution(
        "I204983213",
        "harbin-institute-of-technology",
        "Harbin Institute of Technology",
    ),
    OpenAlexInstitution("I82880672", "beihang", "Beihang University"),
    OpenAlexInstitution("I40120149", "oxford", "University of Oxford"),
    OpenAlexInstitution("I35440088", "ethz", "ETH Zurich"),
    OpenAlexInstitution(
        "I4405261251",
        "hkust-gz2",
        "The Hong Kong University of Science and Technology (Guangzhou)",
    ),
    OpenAlexInstitution("I14243506", "polyuhk", "The Hong Kong Polytechnic University"),
    OpenAlexInstitution("I62916508", "tum", "Technical University of Munich"),
    OpenAlexInstitution("I78988378", "ruc", "Renmin University of China"),
    OpenAlexInstitution("I136199984", "harvard", "Harvard University"),
    OpenAlexInstitution("I139264467", "snu", "Seoul National University"),
    OpenAlexInstitution(
        "I36258959", "ucsandiego", "University of California San Diego"
    ),
    OpenAlexInstitution("I157773358", "sunyatsen", "Sun Yat-sen University"),
    OpenAlexInstitution("I130701444", "georgiatech", "Georgia Institute of Technology"),
    OpenAlexInstitution("I57206974", "newyorkuniversity", "New York University"),
    OpenAlexInstitution("I201448701", "uw", "University of Washington"),
    OpenAlexInstitution(
        "I4210113480",
        "mbzuai",
        "Mohamed bin Zayed University of Artificial Intelligence",
    ),
    OpenAlexInstitution("I161318765", "ucla", "University of California, Los Angeles"),
    OpenAlexInstitution(
        "I1174212",
        "usc",
        "University of Southern California",
    ),
    OpenAlexInstitution("I86519309", "utexas", "The University of Texas at Austin"),
    OpenAlexInstitution("I20089843", "princetonu", "Princeton University"),
    OpenAlexInstitution("I37461747", "wuhanuniversity", "Wuhan University"),
    OpenAlexInstitution(
        "I241749", "university-of-cambridge", "University of Cambridge"
    ),
    OpenAlexInstitution(
        "I47720641",
        "huazhong-university",
        "Huazhong University of Science and Technology",
    ),
    OpenAlexInstitution("I145311948", "johnshopkins", "Johns Hopkins University"),
    OpenAlexInstitution(
        "I1294671590", "cnrs", "Centre National de la Recherche Scientifique"
    ),
    OpenAlexInstitution(
        "I66946132", "umaryland", "University of Maryland, College Park"
    ),
    OpenAlexInstitution("I27837315", "umich", "University of Michigan"),
    OpenAlexInstitution(
        "I139759216", "bupt", "Beijing University of Posts and Telecommunications"
    ),
    OpenAlexInstitution("I168719708", "cityu-hongkong", "City University of Hong Kong"),
    OpenAlexInstitution(
        "I87445476", "xianjiaotonguniversity", "Xi'an Jiaotong University"
    ),
    OpenAlexInstitution(
        "I47508984", "imperialcollegelondon", "Imperial College London"
    ),
    OpenAlexInstitution("I185261750", "universityoftoronto", "University of Toronto"),
    OpenAlexInstitution(
        "I45129253", "universitycollegelondon", "University College London"
    ),
    OpenAlexInstitution("I4405279436", "sii-research", "Shanghai Innovation Institute"),
    OpenAlexInstitution(
        "I4210116924", "cuhksz", "Chinese University of Hong Kong, Shenzhen"
    ),
    OpenAlexInstitution("I135310074", "uw-madison", "University of Wisconsin–Madison"),
    OpenAlexInstitution("I78577930", "columbia-university", "Columbia University"),
    OpenAlexInstitution("I5124864", "epfl", "EPFL"),
    OpenAlexInstitution(
        "I150229711",
        "uestc",
        "University of Electronic Science and Technology of China",
    ),
    OpenAlexInstitution("I74801974", "university-of-tokyo", "The University of Tokyo"),
    OpenAlexInstitution("I116953780", "tongjiuniversity", "Tongji University"),
    OpenAlexInstitution("I32971472", "yaleuniversity", "Yale University"),
    OpenAlexInstitution("I79576946", "upenn", "University of Pennsylvania"),
    OpenAlexInstitution("I205783295", "cornell", "Cornell University"),
    OpenAlexInstitution(
        "I66867065",
        "east-china-normal-university",
        "East China Normal University",
    ),
    OpenAlexInstitution("I76569877", "southeast-university", "Southeast University"),
    OpenAlexInstitution(
        "I125839683",
        "beijing-institute-of-technology",
        "Beijing Institute of Technology",
    ),
    OpenAlexInstitution("I219193219", "purdue", "Purdue University"),
    OpenAlexInstitution("I12912129", "northeastern", "Northeastern University"),
    OpenAlexInstitution("I90610280", "cn-scut", "South China University of Technology"),
    OpenAlexInstitution("I3133055985", "westlake-university", "Westlake University"),
    OpenAlexInstitution(
        "I98677209", "universityofedinburgh", "University of Edinburgh"
    ),
    OpenAlexInstitution("I1326498283", "inria", "Inria"),
    OpenAlexInstitution("I205237279", "nankaiuniversity", "Nankai University"),
    OpenAlexInstitution("I193775966", "yonseiworld", "Yonsei University"),
    OpenAlexInstitution(
        "I4210164802", "milaquebec", "Mila - Quebec Artificial Intelligence Institute"
    ),
    OpenAlexInstitution("I197347611", "koreauniversity", "Korea University"),
    OpenAlexInstitution(
        "I4210090176",
        "ict-cas",
        "Institute of Computing Technology, Chinese Academy of Sciences",
    ),
    OpenAlexInstitution("I191208505", "xmu", "Xiamen University"),
    OpenAlexInstitution(
        "I114027177",
        "unc-chapelhill",
        "University of North Carolina at Chapel Hill",
    ),
    OpenAlexInstitution("I180726961", "shenzhenuniversity", "Shenzhen University"),
    OpenAlexInstitution(
        "I4210136793", "peng-cheng-laboratory", "Peng Cheng Laboratory"
    ),
    OpenAlexInstitution(
        "I79891267",
        "singapore-management-university",
        "Singapore Management University",
    ),
    OpenAlexInstitution(
        "I887064364", "university-of-amsterdam", "University of Amsterdam"
    ),
    OpenAlexInstitution("I129604602", "sydney-uni", "The University of Sydney"),
    OpenAlexInstitution(
        "I3045169105", "sustech", "Southern University of Science and Technology"
    ),
    OpenAlexInstitution(
        "I4210100255", "baai", "Beijing Academy of Artificial Intelligence"
    ),
    OpenAlexInstitution("I151746483", "uwaterloo", "University of Waterloo"),
    OpenAlexInstitution("I56590836", "monash", "Monash University"),
    OpenAlexInstitution("I5023651", "mcgill-university", "McGill University"),
    OpenAlexInstitution("I162868743", "tianjin-university", "Tianjin University"),
    OpenAlexInstitution("I130769515", "pennstate", "Pennsylvania State University"),
    OpenAlexInstitution("I8204097", "lmu-munich", "LMU Munich"),
    OpenAlexInstitution("I91045830", "texasamuniversity", "Texas A&M University"),
    OpenAlexInstitution("I40347166", "university-of-chicago", "University of Chicago"),
    OpenAlexInstitution(
        "I36399199", "njust", "Nanjing University of Science and Technology"
    ),
    OpenAlexInstitution("I141945490", "ubc-v", "University of British Columbia"),
    OpenAlexInstitution("I4403386549", "mcml", "Munich Center for Machine Learning"),
    OpenAlexInstitution("I154099455", "shandong-university", "Shandong University"),
    OpenAlexInstitution(
        "I111979921", "northwestern-university", "Northwestern University"
    ),
    OpenAlexInstitution(
        "I30809798", "shanghaitech-university", "ShanghaiTech University"
    ),
    OpenAlexInstitution(
        "I174306211", "technion", "Technion – Israel Institute of Technology"
    ),
    OpenAlexInstitution(
        "I70931966", "universite-de-montreal", "Université de Montréal"
    ),
    OpenAlexInstitution(
        "I16733864", "national-taiwan-university", "National Taiwan University"
    ),
    OpenAlexInstitution(
        "I170215575", "nudt", "National University of Defense Technology"
    ),
    OpenAlexInstitution("I52357470", "ohiostate", "The Ohio State University"),
    OpenAlexInstitution("I204512498", "university-of-macau", "University of Macau"),
    OpenAlexInstitution(
        "I71920554", "kaust", "King Abdullah University of Science and Technology"
    ),
    OpenAlexInstitution("I4210127509", "vector-institute", "Vector Institute"),
    OpenAlexInstitution("I31746571", "unsw-sydney", "UNSW Sydney"),
    OpenAlexInstitution(
        "I51556381", "university-of-virginia", "University of Virginia"
    ),
    OpenAlexInstitution(
        "I17145004",
        "northwestern-polytechnical-university",
        "Northwestern Polytechnical University",
    ),
    OpenAlexInstitution(
        "I55732556", "arizona-state-university", "Arizona State University"
    ),
    OpenAlexInstitution(
        "I8087733",
        "eberhard-karls-universitat-tubingen",
        "Eberhard Karls Universität Tübingen",
    ),
    OpenAlexInstitution("I102322142", "rutgersu", "Rutgers University"),
    OpenAlexInstitution("I149594827", "xidian-university", "Xidian University"),
    OpenAlexInstitution(
        "I123900574", "postech", "Pohang University of Science and Technology"
    ),
    OpenAlexInstitution("I24185976", "sichuan-university", "Sichuan University"),
    OpenAlexInstitution("I21193070", "bjtuniversity", "Beijing Jiaotong University"),
    OpenAlexInstitution(
        "I31512782", "tu-darmstadt", "Technische Universität Darmstadt"
    ),
    OpenAlexInstitution("I16391192", "tau", "Tel Aviv University"),
    OpenAlexInstitution("I170897317", "duke-university", "Duke University"),
    OpenAlexInstitution("I859038795", "virginiatech", "Virginia Tech"),
    OpenAlexInstitution(
        "I124055696", "university-of-copenhagen", "University of Copenhagen"
    ),
    OpenAlexInstitution("I27804330", "brownu", "Brown University"),
    OpenAlexInstitution("I39422238", "uic-ai-lab", "University of Illinois Chicago"),
    OpenAlexInstitution("I24603500", "umass", "University of Massachusetts Amherst"),
    OpenAlexInstitution("I194450716", "jilinuniversity001", "Jilin University"),
    OpenAlexInstitution(
        "I27357992",
        "dalian-university-of-technology",
        "Dalian University of Technology",
    ),
    OpenAlexInstitution(
        "I4210156404",
        "iie-cas",
        "Institute of Information Engineering, Chinese Academy of Sciences",
    ),
    OpenAlexInstitution(
        "I139660479", "central-south-university", "Central South University"
    ),
    OpenAlexInstitution(
        "I4210145761",
        "siat-cas",
        "Shenzhen Institutes of Advanced Technology, Chinese Academy of Sciences",
    ),
    OpenAlexInstitution("I122411786", "caltech", "California Institute of Technology"),
    OpenAlexInstitution(
        "I87216513", "michigan-state-university", "Michigan State University"
    ),
    OpenAlexInstitution("I106165777", "ucf-ai-llms", "University of Central Florida"),
    OpenAlexInstitution(
        "I130238516", "university-of-minnesota", "University of Minnesota"
    ),
    OpenAlexInstitution("I165779595", "unimelb-nlp", "The University of Melbourne"),
    OpenAlexInstitution(
        "I154570441",
        "university-of-california-santa-barbara",
        "University of California, Santa Barbara",
    ),
    OpenAlexInstitution(
        "I4210156221", "allenai", "Allen Institute for Artificial Intelligence"
    ),
    OpenAlexInstitution(
        "I59553526", "stony-brook-university", "Stony Brook University"
    ),
    OpenAlexInstitution(
        "I107639228", "university-of-notre-dame", "University of Notre Dame"
    ),
    OpenAlexInstitution("I183935753", "kcl", "King's College London"),
    OpenAlexInstitution(
        "I115228651", "a-star", "Agency for Science, Technology and Research"
    ),
    OpenAlexInstitution("I4210110652", "riken", "RIKEN"),
    OpenAlexInstitution("I5681781", "adelaideuniversity", "The University of Adelaide"),
    # Companies.
    OpenAlexInstitution("I45928872", "alibabagroup", "Alibaba Group"),
    OpenAlexInstitution("I4210095624", "alibabagroup", "Alibaba Group (United States)"),
    OpenAlexInstitution("I4405281272", "alibaba-damo-academy", "DAMO Academy"),
    OpenAlexInstitution("I2250653659", "tencent", "Tencent"),
    OpenAlexInstitution("I1290206253", "microsoft", "Microsoft"),
    OpenAlexInstitution("I4210113369", "microsoftresearch", "Microsoft Research Asia"),
    OpenAlexInstitution(
        "I4210164937", "microsoftresearch", "Microsoft Research (United Kingdom)"
    ),
    OpenAlexInstitution("I1291425158", "google", "Google"),
    OpenAlexInstitution("I4210090411", "deepmind", "Google DeepMind"),
    OpenAlexInstitution("I2250955327", "huawei", "Huawei"),
    OpenAlexInstitution("I4405256866", "bytedance", "ByteDance"),
    OpenAlexInstitution("I1311688040", "amazon", "Amazon"),
    OpenAlexInstitution("I4210127875", "nvidia", "NVIDIA"),
    OpenAlexInstitution("I1304085615", "nvidia", "NVIDIA (United Kingdom)"),
    OpenAlexInstitution("I4405270328", "antgroup", "Ant Group"),
    OpenAlexInstitution("I1306409833", "adobe", "Adobe"),
    OpenAlexInstitution("I1341412227", "ibm", "IBM"),
    OpenAlexInstitution("I98301712", "baidu", "Baidu"),
    OpenAlexInstitution("I4405259410", "meituan", "Meituan"),
    OpenAlexInstitution("I4210114444", "facebook", "Meta"),
    OpenAlexInstitution("I4210111288", "facebook", "Meta (United Kingdom)"),
    OpenAlexInstitution("I4401726859", "kuaishou", "Kuaishou"),
    OpenAlexInstitution("I4210155268", "salesforce", "Salesforce"),
    OpenAlexInstitution("I4210153776", "apple", "Apple"),
    OpenAlexInstitution("I4401726856", "xiaohongshuai", "Xiaohongshu"),
    OpenAlexInstitution("I862669128", "xiaomi", "Xiaomi"),
    OpenAlexInstitution("I4401727009", "sensetime", "SenseTime"),
    OpenAlexInstitution("I2250650973", "samsung", "Samsung"),
    OpenAlexInstitution("I60922564", "naver", "NAVER"),
    OpenAlexInstitution("I4405260609", "naver", "NAVER Cloud"),
    OpenAlexInstitution("I4210087596", "qualcomm", "Qualcomm"),
    OpenAlexInstitution("I4210142583", "snap-research", "Snap"),
    OpenAlexInstitution("I4210103986", "jingdong1", "JD.com"),
    OpenAlexInstitution("I1343180700", "intel", "Intel"),
    OpenAlexInstitution("I4405258446", "lgai-exaone", "LG AI Research"),
    OpenAlexInstitution("I4401726847", "coherelabs", "Cohere"),
    OpenAlexInstitution("I4210161460", "openai", "OpenAI"),
    OpenAlexInstitution("I4405260255", "stepfun-ai", "StepFun"),
    OpenAlexInstitution("I4210143797", "sony", "Sony"),
)

BY_OPENALEX_ID = {item.openalex_id: item for item in OPENALEX_INSTITUTIONS}

if len(BY_OPENALEX_ID) != len(OPENALEX_INSTITUTIONS):
    raise RuntimeError("OpenAlex institution IDs must be unique")


def organization_slug_for(openalex_id: str) -> str | None:
    """Return the organization slug for an OpenAlex institution ID or URL."""
    return (
        item.slug
        if (item := BY_OPENALEX_ID.get(openalex_id.rsplit("/", 1)[-1]))
        else None
    )
