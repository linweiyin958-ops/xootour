-- ============================================================
-- XOOTOUR Beijing Database Schema
-- 景点系统 + 5大品类门店系统（美食/酒店/景点/购物/娱乐）
-- ============================================================

CREATE DATABASE IF NOT EXISTS `xootour_chongqing` DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE `xootour_chongqing`;

-- ============================================================
-- 一、景点系统（Tour Spot）
-- ============================================================

DROP TABLE IF EXISTS `tour_spot_package`;
DROP TABLE IF EXISTS `tour_spot_facility`;
DROP TABLE IF EXISTS `tour_spot_route`;
DROP TABLE IF EXISTS `tour_spot_feature`;
DROP TABLE IF EXISTS `tour_spot_banner`;
DROP TABLE IF EXISTS `tour_spot_info`;
DROP TABLE IF EXISTS `tour_spot`;

CREATE TABLE `tour_spot` (
    `id` INT PRIMARY KEY AUTO_INCREMENT,
    `name` VARCHAR(200) NOT NULL COMMENT '中文全名',
    `subtitle` VARCHAR(200) COMMENT '英文全名/副标题',
    `city_id` INT NOT NULL DEFAULT 2 COMMENT '城市ID(重庆=2)',
    `cover_img` VARCHAR(500) COMMENT '封面图URL',
    `seo_desc` VARCHAR(500) COMMENT 'SEO描述',
    `base_price` DECIMAL(10,2) DEFAULT 0.00 COMMENT '起步参考价格',
    `rating` DECIMAL(2,1) DEFAULT 0.0 COMMENT '综合评分',
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='景点主表';

CREATE TABLE `tour_spot_info` (
    `id` INT PRIMARY KEY AUTO_INCREMENT,
    `spot_id` INT NOT NULL COMMENT '关联景点ID',
    `district` VARCHAR(100) COMMENT '行政区',
    `address_zh` TEXT COMMENT '中文详细地址',
    `address_en` TEXT COMMENT '英文详细地址',
    `lat` DECIMAL(10,7) COMMENT '纬度',
    `lng` DECIMAL(10,7) COMMENT '经度',
    `summary_zh` TEXT COMMENT '中文详情介绍',
    `summary_en` TEXT COMMENT '英文详情介绍',
    `open_hours` TEXT COMMENT '开放时间',
    `transportation` TEXT COMMENT '交通方式',
    `visit_notice` TEXT COMMENT '参观须知',
    `best_visit_season` VARCHAR(100) COMMENT '最佳游玩季节',
    `photo_spots` JSON COMMENT '打卡机位JSON',
    `crowd_tags` JSON COMMENT '适合人群标签JSON',
    `source_platform` VARCHAR(50) COMMENT '数据源平台',
    `source_note_ids` JSON COMMENT '数据源链接JSON',
    `data_collected_at` TIMESTAMP NULL COMMENT '数据采集时间',
    `data_quality_score` DECIMAL(3,2) COMMENT '数据质量评分0-1',
    `is_ai_generated` BOOLEAN DEFAULT TRUE COMMENT '是否AI生成',
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY `uk_spot_id` (`spot_id`),
    CONSTRAINT `fk_spot_info_spot` FOREIGN KEY (`spot_id`) REFERENCES `tour_spot`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='景点概况表';

CREATE TABLE `tour_spot_banner` (
    `id` INT PRIMARY KEY AUTO_INCREMENT,
    `spot_id` INT NOT NULL COMMENT '关联景点ID',
    `image_url` VARCHAR(500) NOT NULL COMMENT '图片URL',
    `sort_order` INT DEFAULT 0 COMMENT '排序',
    `photo_credit` VARCHAR(100) COMMENT '图片来源标注',
    CONSTRAINT `fk_banner_spot` FOREIGN KEY (`spot_id`) REFERENCES `tour_spot`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='景点画廊';

CREATE TABLE `tour_spot_feature` (
    `id` INT PRIMARY KEY AUTO_INCREMENT,
    `spot_id` INT NOT NULL COMMENT '关联景点ID',
    `title` VARCHAR(150) NOT NULL COMMENT '亮点标题',
    `description` TEXT NOT NULL COMMENT '亮点描述',
    CONSTRAINT `fk_feature_spot` FOREIGN KEY (`spot_id`) REFERENCES `tour_spot`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='景点亮点体验';

CREATE TABLE `tour_spot_route` (
    `id` INT PRIMARY KEY AUTO_INCREMENT,
    `spot_id` INT NOT NULL COMMENT '关联景点ID',
    `route_name` VARCHAR(200) NOT NULL COMMENT '路线名称',
    `duration_hours` DECIMAL(3,1) COMMENT '预计游玩时长',
    `route_nodes` JSON NOT NULL COMMENT '打卡节点JSON',
    `description` TEXT COMMENT '路线描述与避坑指南',
    CONSTRAINT `fk_route_spot` FOREIGN KEY (`spot_id`) REFERENCES `tour_spot`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='景点游玩路线';

CREATE TABLE `tour_spot_facility` (
    `id` INT PRIMARY KEY AUTO_INCREMENT,
    `spot_id` INT NOT NULL COMMENT '关联景点ID',
    `facility_name` VARCHAR(100) NOT NULL COMMENT '设施名称',
    `is_bold` BOOLEAN DEFAULT FALSE COMMENT '是否加粗显示',
    `description` VARCHAR(255) COMMENT '补充说明',
    CONSTRAINT `fk_facility_spot` FOREIGN KEY (`spot_id`) REFERENCES `tour_spot`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='景点服务设施';

CREATE TABLE `tour_spot_package` (
    `id` INT PRIMARY KEY AUTO_INCREMENT,
    `spot_id` INT NOT NULL COMMENT '关联景点ID',
    `package_name` VARCHAR(200) NOT NULL COMMENT '套餐名称',
    `price` DECIMAL(10,2) NOT NULL COMMENT '价格',
    `description` TEXT COMMENT '套餐说明',
    `currency` VARCHAR(10) DEFAULT 'RMB' COMMENT '币种',
    CONSTRAINT `fk_package_spot` FOREIGN KEY (`spot_id`) REFERENCES `tour_spot`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='景点门票套餐';


-- ============================================================
-- 二、门店品类分类表（Store Category）- 5品类
-- ============================================================

DROP TABLE IF EXISTS `store_product_image`;
DROP TABLE IF EXISTS `store_product`;
DROP TABLE IF EXISTS `store_facility`;
DROP TABLE IF EXISTS `store_banner`;
DROP TABLE IF EXISTS `store_info`;
DROP TABLE IF EXISTS `store`;
DROP TABLE IF EXISTS `store_category`;

CREATE TABLE `store_category` (
    `id` INT PRIMARY KEY AUTO_INCREMENT,
    `name_zh` VARCHAR(100) NOT NULL COMMENT '品类中文名',
    `name_en` VARCHAR(100) NOT NULL COMMENT '品类英文名',
    `icon` VARCHAR(100) COMMENT '图标标识',
    `sort_order` INT DEFAULT 0 COMMENT '排序',
    `description` VARCHAR(500) COMMENT '品类描述',
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='门店品类分类';

INSERT INTO `store_category` (`id`, `name_zh`, `name_en`, `sort_order`, `description`) VALUES
(1, '美食', 'Food', 1, '重庆美食门店，覆盖火锅/小面/江湖菜/烧烤/老字号及各地菜系'),
(2, '酒店', 'Hotel', 2, '重庆住宿服务，覆盖星级酒店/江景民宿/山城客栈/青年旅舍'),
(3, '景点', 'Attraction', 3, '重庆旅游景点，覆盖5A/4A景区/博物馆/公园/古镇/主题乐园'),
(4, '购物', 'Shopping', 4, '重庆购物场所，覆盖商圈百货/特色街区/文创市集'),
(5, '娱乐', 'Entertainment', 5, '重庆娱乐场所，覆盖酒吧/KTV/密室/剧本杀/演出/相声/温泉');


-- ============================================================
-- 三、门店系统（Store）
-- ============================================================

CREATE TABLE `store` (
    `id` INT PRIMARY KEY AUTO_INCREMENT,
    `name_zh` VARCHAR(200) NOT NULL COMMENT '门店中文名',
    `name_en` VARCHAR(200) COMMENT '门店英文名',
    `category_id` INT NOT NULL COMMENT '品类ID',
    `city_id` INT NOT NULL DEFAULT 2 COMMENT '城市ID(重庆=2)',
    `cover_img` VARCHAR(500) COMMENT '封面图URL',
    `seo_desc` VARCHAR(500) COMMENT 'SEO描述',
    `price_range` VARCHAR(100) COMMENT '价格区间(如:人均¥100-200)',
    `rating` DECIMAL(2,1) DEFAULT 0.0 COMMENT '综合评分',
    `review_count` INT DEFAULT 0 COMMENT '评论数',
    `ranking_desc` VARCHAR(200) COMMENT '排名描述',
    `cuisine_tags` JSON COMMENT '菜系标签JSON',
    `michelin_status` INT DEFAULT 0 COMMENT '米其林星级(0=无)',
    `source_platform` VARCHAR(50) COMMENT '数据源平台',
    `data_quality_score` DECIMAL(3,2) DEFAULT 0.00 COMMENT '数据质量评分0-1',
    `is_ai_generated` BOOLEAN DEFAULT TRUE COMMENT '是否AI生成',
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX `idx_category` (`category_id`),
    INDEX `idx_city` (`city_id`),
    CONSTRAINT `fk_store_category` FOREIGN KEY (`category_id`) REFERENCES `store_category`(`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='门店主表';

CREATE TABLE `store_info` (
    `id` INT PRIMARY KEY AUTO_INCREMENT,
    `store_id` INT NOT NULL COMMENT '关联门店ID',
    `category_id` INT NOT NULL COMMENT '品类ID',
    `amap_id` VARCHAR(50) COMMENT '高德地图POI ID',
    `district` VARCHAR(100) COMMENT '行政区',
    `address_zh` TEXT COMMENT '中文详细地址',
    `address_en` TEXT COMMENT '英文详细地址',
    `lat` DECIMAL(10,7) COMMENT '纬度',
    `lng` DECIMAL(10,7) COMMENT '经度',
    `phone` VARCHAR(50) COMMENT '联系电话',
    `website` VARCHAR(500) COMMENT '官方网站',
    `open_hours` TEXT COMMENT '营业时间',
    `summary_zh` TEXT COMMENT '中文详情介绍',
    `summary_en` TEXT COMMENT '英文详情介绍',
    `visit_notice` TEXT COMMENT '消费须知/注意事项',
    `signature_items` JSON COMMENT '招牌/特色项JSON(如招牌菜、特色房型等)',
    `tags` JSON COMMENT '标签JSON(如:外宾友好,可刷外卡,有英文菜单)',
    `category_specific_fields` JSON COMMENT '品类专用字段(按store-prompts.md规范)',
    `subratings` JSON COMMENT '子评分JSON(如食物/服务/性价比)',
    `features` JSON COMMENT '特征JSON',
    `photos_count` INT DEFAULT 0 COMMENT '照片数量',
    `source_platform` VARCHAR(50) COMMENT '数据源平台',
    `source_urls` JSON COMMENT '数据源链接JSON',
    `data_collected_at` TIMESTAMP NULL COMMENT '数据采集时间',
    `data_quality_score` DECIMAL(3,2) COMMENT '数据质量评分0-1',
    `is_ai_generated` BOOLEAN DEFAULT TRUE COMMENT '是否AI生成',
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY `uk_store_id` (`store_id`),
    CONSTRAINT `fk_info_store` FOREIGN KEY (`store_id`) REFERENCES `store`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='门店概况表';

CREATE TABLE `store_banner` (
    `id` INT PRIMARY KEY AUTO_INCREMENT,
    `store_id` INT NOT NULL COMMENT '关联门店ID',
    `image_url` VARCHAR(500) NOT NULL COMMENT '图片URL',
    `sort_order` INT DEFAULT 0 COMMENT '排序',
    `caption` VARCHAR(255) COMMENT '图片说明',
    `photo_credit` VARCHAR(100) COMMENT '图片来源标注',
    CONSTRAINT `fk_store_banner_store` FOREIGN KEY (`store_id`) REFERENCES `store`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='门店画廊';

CREATE TABLE `store_product` (
    `id` INT PRIMARY KEY AUTO_INCREMENT,
    `store_id` INT NOT NULL COMMENT '关联门店ID',
    `product_name` VARCHAR(200) NOT NULL COMMENT '产品/菜品/房型名称',
    `price` DECIMAL(10,2) COMMENT '价格',
    `description` TEXT COMMENT '产品描述/菜品介绍',
    `currency` VARCHAR(10) DEFAULT 'RMB' COMMENT '币种',
    `is_signature` BOOLEAN DEFAULT FALSE COMMENT '是否招牌/推荐',
    `sort_order` INT DEFAULT 0 COMMENT '排序',
    CONSTRAINT `fk_product_store` FOREIGN KEY (`store_id`) REFERENCES `store`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='门店产品/菜品/房型';

CREATE TABLE `store_product_image` (
    `id` INT PRIMARY KEY AUTO_INCREMENT,
    `product_id` INT NOT NULL COMMENT '关联产品ID',
    `image_url` VARCHAR(500) NOT NULL COMMENT '图片URL',
    `sort_order` INT DEFAULT 0 COMMENT '排序',
    CONSTRAINT `fk_product_image_product` FOREIGN KEY (`product_id`) REFERENCES `store_product`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='门店产品图片';

CREATE TABLE `store_facility` (
    `id` INT PRIMARY KEY AUTO_INCREMENT,
    `store_id` INT NOT NULL COMMENT '关联门店ID',
    `category` VARCHAR(100) COMMENT '设施分类',
    `facility_name` VARCHAR(100) NOT NULL COMMENT '设施名称',
    `is_bold` BOOLEAN DEFAULT FALSE COMMENT '是否加粗显示',
    `description` VARCHAR(255) COMMENT '补充说明',
    CONSTRAINT `fk_store_facility_store` FOREIGN KEY (`store_id`) REFERENCES `store`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='门店服务设施';
