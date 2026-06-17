PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS `tour_spot` (
    `id` INTEGER PRIMARY KEY,
    `name` TEXT NOT NULL,
    `subtitle` TEXT,
    `city_id` INTEGER NOT NULL DEFAULT 2,
    `cover_img` TEXT,
    `seo_desc` TEXT,
    `base_price` REAL DEFAULT 0.00,
    `rating` REAL DEFAULT 0.0,
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS `tour_spot_info` (
    `id` INTEGER PRIMARY KEY,
    `spot_id` INTEGER NOT NULL UNIQUE,
    `district` TEXT,
    `address_zh` TEXT,
    `address_en` TEXT,
    `lat` REAL,
    `lng` REAL,
    `summary_zh` TEXT,
    `summary_en` TEXT,
    `open_hours` TEXT,
    `transportation` TEXT,
    `visit_notice` TEXT,
    `best_visit_season` TEXT,
    `photo_spots` TEXT,
    `crowd_tags` TEXT,
    `source_platform` TEXT,
    `source_note_ids` TEXT,
    `data_collected_at` TIMESTAMP,
    `data_quality_score` REAL,
    `is_ai_generated` INTEGER DEFAULT 1,
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (`spot_id`) REFERENCES `tour_spot`(`id`) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS `tour_spot_banner` (
    `id` INTEGER PRIMARY KEY,
    `spot_id` INTEGER NOT NULL,
    `image_url` TEXT NOT NULL,
    `sort_order` INTEGER DEFAULT 0,
    `photo_credit` TEXT,
    FOREIGN KEY (`spot_id`) REFERENCES `tour_spot`(`id`) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS `tour_spot_feature` (
    `id` INTEGER PRIMARY KEY,
    `spot_id` INTEGER NOT NULL,
    `title` TEXT NOT NULL,
    `description` TEXT NOT NULL,
    FOREIGN KEY (`spot_id`) REFERENCES `tour_spot`(`id`) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS `tour_spot_route` (
    `id` INTEGER PRIMARY KEY,
    `spot_id` INTEGER NOT NULL,
    `route_name` TEXT NOT NULL,
    `duration_hours` REAL,
    `route_nodes` TEXT NOT NULL,
    `description` TEXT,
    FOREIGN KEY (`spot_id`) REFERENCES `tour_spot`(`id`) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS `tour_spot_facility` (
    `id` INTEGER PRIMARY KEY,
    `spot_id` INTEGER NOT NULL,
    `facility_name` TEXT NOT NULL,
    `is_bold` INTEGER DEFAULT 0,
    `description` TEXT,
    FOREIGN KEY (`spot_id`) REFERENCES `tour_spot`(`id`) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS `tour_spot_package` (
    `id` INTEGER PRIMARY KEY,
    `spot_id` INTEGER NOT NULL,
    `package_name` TEXT NOT NULL,
    `price` REAL NOT NULL,
    `description` TEXT,
    `currency` TEXT DEFAULT 'RMB',
    FOREIGN KEY (`spot_id`) REFERENCES `tour_spot`(`id`) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS `store_category` (
    `id` INTEGER PRIMARY KEY,
    `name_zh` TEXT NOT NULL,
    `name_en` TEXT NOT NULL,
    `icon` TEXT,
    `sort_order` INTEGER DEFAULT 0,
    `description` TEXT,
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

INSERT OR IGNORE INTO `store_category` (`id`, `name_zh`, `name_en`, `sort_order`, `description`) VALUES
(1, '美食', 'Food', 1, '三亚美食门店，覆盖海鲜/海南菜/椰子鸡/糟粕醋/清补凉及各地菜系'),
(2, '酒店', 'Hotel', 2, '三亚住宿服务，覆盖星级酒店/海景民宿/度假村/青年旅舍'),
(3, '景点', 'Attraction', 3, '三亚旅游景点，覆盖5A/4A景区/海滩/海岛/热带雨林/主题乐园'),
(4, '购物', 'Shopping', 4, '三亚购物场所，覆盖免税店/商圈百货/海鲜市场/夜市/文创市集'),
(5, '娱乐', 'Entertainment', 5, '三亚娱乐场所，覆盖酒吧/KTV/水上运动/潜水/游艇/水疗/夜店');

CREATE TABLE IF NOT EXISTS `store` (
    `id` INTEGER PRIMARY KEY,
    `name_zh` TEXT NOT NULL,
    `name_en` TEXT,
    `category_id` INTEGER NOT NULL,
    `city_id` INTEGER NOT NULL DEFAULT 2,
    `cover_img` TEXT,
    `seo_desc` TEXT,
    `price_range` TEXT,
    `rating` REAL DEFAULT 0.0,
    `review_count` INTEGER DEFAULT 0,
    `ranking_desc` TEXT,
    `cuisine_tags` TEXT,
    `michelin_status` INTEGER DEFAULT 0,
    `source_platform` TEXT,
    `data_quality_score` REAL DEFAULT 0.00,
    `is_ai_generated` INTEGER DEFAULT 1,
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (`category_id`) REFERENCES `store_category`(`id`)
);

CREATE TABLE IF NOT EXISTS `store_info` (
    `id` INTEGER PRIMARY KEY,
    `store_id` INTEGER NOT NULL UNIQUE,
    `category_id` INTEGER NOT NULL,
    `amap_id` TEXT,
    `district` TEXT,
    `address_zh` TEXT,
    `address_en` TEXT,
    `lat` REAL,
    `lng` REAL,
    `phone` TEXT,
    `website` TEXT,
    `open_hours` TEXT,
    `summary_zh` TEXT,
    `summary_en` TEXT,
    `visit_notice` TEXT,
    `signature_items` TEXT,
    `tags` TEXT,
    `category_specific_fields` TEXT,
    `subratings` TEXT,
    `features` TEXT,
    `photos_count` INTEGER DEFAULT 0,
    `source_platform` TEXT,
    `source_urls` TEXT,
    `data_collected_at` TIMESTAMP,
    `data_quality_score` REAL,
    `is_ai_generated` INTEGER DEFAULT 1,
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (`store_id`) REFERENCES `store`(`id`) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS `store_banner` (
    `id` INTEGER PRIMARY KEY,
    `store_id` INTEGER NOT NULL,
    `image_url` TEXT NOT NULL,
    `sort_order` INTEGER DEFAULT 0,
    `caption` TEXT,
    `photo_credit` TEXT,
    FOREIGN KEY (`store_id`) REFERENCES `store`(`id`) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS `store_product` (
    `id` INTEGER PRIMARY KEY,
    `store_id` INTEGER NOT NULL,
    `product_name` TEXT NOT NULL,
    `price` REAL,
    `description` TEXT,
    `currency` TEXT DEFAULT 'RMB',
    `is_signature` INTEGER DEFAULT 0,
    `sort_order` INTEGER DEFAULT 0,
    FOREIGN KEY (`store_id`) REFERENCES `store`(`id`) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS `store_product_image` (
    `id` INTEGER PRIMARY KEY,
    `product_id` INTEGER NOT NULL,
    `image_url` TEXT NOT NULL,
    `sort_order` INTEGER DEFAULT 0,
    FOREIGN KEY (`product_id`) REFERENCES `store_product`(`id`) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS `store_facility` (
    `id` INTEGER PRIMARY KEY,
    `store_id` INTEGER NOT NULL,
    `category` TEXT,
    `facility_name` TEXT NOT NULL,
    `is_bold` INTEGER DEFAULT 0,
    `description` TEXT,
    FOREIGN KEY (`store_id`) REFERENCES `store`(`id`) ON DELETE CASCADE
);
