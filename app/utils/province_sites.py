"""各省自然资源主管部门招考或人事栏目的采集配置。"""

from typing import Any, TypedDict


class ProvinceSiteConfig(TypedDict):
    """单个省级自然资源网站的列表发现配置。"""

    province: str
    agency_name: str
    list_url: str
    item_selector: str
    next_page: dict[str, Any]


# CSS 选择器优先覆盖栏目正文列表，同时保留较宽的 li a 兜底以适应小幅改版。
# 下一页规则统一声明选择器；抓取器还会按“下一页”文字做第二层兜底。
PROVINCE_SITES: dict[str, ProvinceSiteConfig] = {
    "陕西": {
        "province": "陕西",
        "agency_name": "陕西省自然资源厅",
        "list_url": "https://zrzyt.shaanxi.gov.cn/news/tzgg/",
        "item_selector": ".list li a, .news-list li a, .tzgg li a, li a[href]",
        "next_page": {
            "type": "selector",
            "selector": "a[title*='下一页'], a.next, .pagination a.next",
            "max_pages": 6,
        },
    },
    "湖北": {
        "province": "湖北",
        "agency_name": "湖北省自然资源厅",
        "list_url": "https://zrzyt.hubei.gov.cn/fbjd/xxgkml/zkly/",
        "item_selector": ".info-list li a, .list li a, .xxgk-list li a, li a[href]",
        "next_page": {
            "type": "selector",
            "selector": "a[title*='下一页'], a.next, .page a.next",
            "max_pages": 6,
        },
    },
    "四川": {
        "province": "四川",
        "agency_name": "四川省自然资源厅",
        "list_url": "https://dnr.sc.gov.cn/scdnr/sczkly/sc_gkzd_list.shtml",
        "item_selector": ".list li a, .gk-list li a, .news_list li a, li a[href]",
        "next_page": {
            "type": "selector",
            "selector": "a[title*='下一页'], a.next, .page-next a",
            "max_pages": 6,
        },
    },
    "广东": {
        "province": "广东",
        "agency_name": "广东省自然资源厅",
        "list_url": "https://nr.gd.gov.cn/zwgknew/rsjy/sydwzp/",
        "item_selector": ".news_list li a, .list li a, .content-list li a, li a[href]",
        "next_page": {
            "type": "selector",
            "selector": "a[title*='下一页'], a.next, .pagination a.next",
            "max_pages": 6,
        },
    },
    "浙江": {
        "province": "浙江",
        "agency_name": "浙江省自然资源厅",
        "list_url": "https://zrzyt.zj.gov.cn/col/col1289945/index.html",
        "item_selector": ".default_pgContainer a, .news_list li a, .list li a, li a[href]",
        "next_page": {
            "type": "selector",
            "selector": "a[title*='下一页'], a.next, .default_pgNext",
            "max_pages": 6,
        },
    },
    "江苏": {
        "province": "江苏",
        "agency_name": "江苏省自然资源厅",
        "list_url": (
            "https://zrzy.jiangsu.gov.cn/gtxxgk/nrglIndex.action?"
            "classID=8a908254409a391f01409a4b6d38000a"
        ),
        "item_selector": ".list li a, .xxgk-list a, .news_list li a, li a[href]",
        "next_page": {
            "type": "selector",
            "selector": "a[title*='下一页'], a.next, .pagination a.next",
            "max_pages": 6,
        },
    },
    "北京": {
        "province": "北京",
        "agency_name": "北京市规划和自然资源委员会",
        "list_url": "https://ghzrzyw.beijing.gov.cn/zhengwuxinxi/rsxx/sj/",
        "item_selector": ".list li a, .news-list li a, .infolist li a, li a[href]",
        "next_page": {
            "type": "selector",
            "selector": "a[title*='下一页'], a.next, .pagination a.next",
            "max_pages": 6,
        },
    },
    "山东": {
        "province": "山东",
        "agency_name": "山东省自然资源厅",
        "list_url": "https://dnr.shandong.gov.cn/",
        "item_selector": ".list li a, .news-list li a, .tzgg li a, li a[href]",
        "next_page": {
            "type": "selector",
            "selector": "a[title*='下一页'], a.next, .pagination a.next",
            "max_pages": 4,
        },
    },
}

# 其余省级站点的配置位；确认稳定的人事/招考栏目后可移入 PROVINCE_SITES。
RESERVED_PROVINCE_SITES: dict[str, ProvinceSiteConfig | None] = {
    province: None
    for province in (
        "天津", "河北", "山西", "内蒙古", "辽宁", "吉林", "黑龙江", "上海",
        "安徽", "福建", "江西", "河南", "湖南", "广西", "海南", "重庆",
        "贵州", "云南", "西藏", "甘肃", "青海", "宁夏", "新疆",
    )
}
