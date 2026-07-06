# 자동키 번역률 트리

최종 갱신: 2026-07-06 20:25

이 문서는 `maintenance/translation_keys`의 CSV를 스캔해 모드/파일/번역률 순서로 정리한 진행률 표이다.
번역률은 error 판정(empty/token_broken/no_hangul/quote_noise) 제외 기준이다. warning(identical/too_short)은 진행률에 영향 없음.

## 전체 요약

| 항목 | 수량 |
| --- | ---: |
| 모드 폴더 | 51 |
| CSV 파일 | 385 |
| 번역 완료 행 | 104,220 |
| 의심 번역 행 | 2,324 |
| 번역 대상 행 | 106,544 |
| 전체 번역률 | 97.8% |
| 원문 빈 값 행 | 864 |

## 모드/파일/번역률 트리

| 모드 / 파일 | 번역률 | 완료/의심/대상 | 원문 빈 값 | 상태 |
| --- | ---: | ---: | ---: | --- |
| `a_leader_lillian_scarlett__3336442047` | 1.9% | 1 / 53 / 54 | 0 | 진행 중 (의심 53) |
| └─ `0_key.csv` | 1.9% | 1 / 53 / 54 | 0 | 진행 중 (의심 53) |
| `advanced_tech_tree_tooltip__3480431758` | 100.0% | 746 / 0 / 746 | 0 | 완료 |
| └─ `replace/adv_info_tech_tree_replaced_key.csv` | 100.0% | 746 / 0 / 746 | 0 | 완료 |
| `animated_synthetics_portraits_expanded_reborn__1492025820` | 100.0% | 303 / 0 / 303 | 1 | 완료 |
| └─ `extsynths_key.csv` | 100.0% | 303 / 0 / 303 | 1 | 완료 |
| `archaeology_story_pack_4_3__3723865830` | 100.0% | 520 / 0 / 520 | 11 | 완료 |
| └─ `aspmod_key.csv` | 100.0% | 520 / 0 / 520 | 11 | 완료 |
| `arkanna_mirra_the_white_empress_zera_zafe_leader__3756044659` | 100.0% | 8 / 0 / 8 | 0 | 완료 |
| └─ `arkanna_key.csv` | 100.0% | 8 / 0 / 8 | 0 | 완료 |
| `dynamic_mod_menu_3_10__2458024521` | 100.0% | 465 / 0 / 465 | 14 | 완료 |
| └─ `dmm_key.csv` | 100.0% | 465 / 0 / 465 | 14 | 완료 |
| `elves_of_stellaris__915432220` | 100.0% | 28,122 / 0 / 28,122 | 10 | 완료 |
| └─ `Drow_accident_events_key.csv` | 100.0% | 48 / 0 / 48 | 0 | 완료 |
| └─ `Drow_key.csv` | 100.0% | 260 / 0 / 260 | 1 | 완료 |
| └─ `Elven_key.csv` | 100.0% | 268 / 0 / 268 | 2 | 완료 |
| └─ `eos_concepts_key.csv` | 100.0% | 91 / 0 / 91 | 0 | 완료 |
| └─ `eos_nebulae_key.csv` | 100.0% | 10 / 0 / 10 | 0 | 완료 |
| └─ `eos_species_ names_key.csv` | 100.0% | 204 / 0 / 204 | 0 | 완료 |
| └─ `Lhuren_key.csv` | 100.0% | 284 / 0 / 284 | 7 | 완료 |
| └─ `Lunari_key.csv` | 100.0% | 204 / 0 / 204 | 0 | 완료 |
| └─ `namelists/name_list_DROW1_key.csv` | 100.0% | 2,121 / 0 / 2,121 | 0 | 완료 |
| └─ `namelists/name_list_DROW2_key.csv` | 100.0% | 4,314 / 0 / 4,314 | 0 | 완료 |
| └─ `namelists/name_list_DROW3_key.csv` | 100.0% | 1,233 / 0 / 1,233 | 0 | 완료 |
| └─ `namelists/name_list_ELVEN1_key.csv` | 100.0% | 3,024 / 0 / 3,024 | 0 | 완료 |
| └─ `namelists/name_list_ELVEN2_key.csv` | 100.0% | 5,742 / 0 / 5,742 | 0 | 완료 |
| └─ `namelists/name_list_ELVEN3_key.csv` | 100.0% | 814 / 0 / 814 | 0 | 완료 |
| └─ `namelists/name_list_ELVEN4_key.csv` | 100.0% | 915 / 0 / 915 | 0 | 완료 |
| └─ `namelists/name_list_ELVEN5_key.csv` | 100.0% | 4,627 / 0 / 4,627 | 0 | 완료 |
| └─ `namelists/name_list_ELVEN6_key.csv` | 100.0% | 1,832 / 0 / 1,832 | 0 | 완료 |
| └─ `namelists/name_list_ELVEN7_key.csv` | 100.0% | 2,131 / 0 / 2,131 | 0 | 완료 |
| `esc_next_overwrites_component_progression__2653789292` | 100.0% | 165 / 0 / 165 | 0 | 완료 |
| └─ `nh_esc_next_cp_key.csv` | 100.0% | 165 / 0 / 165 | 0 | 완료 |
| `esc_next_overwrites_global_ship_designs__2653699311` | 100.0% | 90 / 0 / 90 | 0 | 완료 |
| └─ `nh_esc_next_gsd_key.csv` | 100.0% | 90 / 0 / 90 | 0 | 완료 |
| `even_more_origins__1998204784` | 100.0% | 74 / 0 / 74 | 0 | 완료 |
| └─ `00_emo_key.csv` | 100.0% | 74 / 0 / 74 | 0 | 완료 |
| `expanded_stellaris_ascension_perks_delta__2976573664` | 96.4% | 563 / 21 / 584 | 2 | 진행 중 (의심 21) |
| └─ `esap_concepts_key.csv` | 23.1% | 3 / 10 / 13 | 0 | 진행 중 (의심 10) |
| └─ `esap_misc_key.csv` | 96.7% | 202 / 7 / 209 | 0 | 진행 중 (의심 7) |
| └─ `esap_key.csv` | 98.5% | 202 / 3 / 205 | 2 | 진행 중 (의심 3) |
| └─ `esap_modifiers_key.csv` | 99.4% | 156 / 1 / 157 | 0 | 진행 중 (의심 1) |
| `expanded_stellaris_traditions__946222466` | 29.4% | 748 / 1,795 / 2,543 | 10 | 진행 중 (의심 1,795) |
| └─ `est_archivist_adopt_key.csv` | 0.0% | 0 / 55 / 55 | 0 | 미시작 |
| └─ `replace/est_replacements_key.csv` | 0.0% | 0 / 27 / 27 | 0 | 미시작 |
| └─ `est_academy_traits_key.csv` | 1.1% | 2 / 185 / 187 | 0 | 진행 중 (의심 185) |
| └─ `est_traditions_key.csv` | 7.0% | 67 / 886 / 953 | 0 | 진행 중 (의심 886) |
| └─ `est_misc_key.csv` | 27.7% | 187 / 489 / 676 | 10 | 진행 중 (의심 489) |
| └─ `est_concepts_key.csv` | 31.8% | 7 / 15 / 22 | 0 | 진행 중 (의심 15) |
| └─ `est_modifiers_key.csv` | 67.4% | 285 / 138 / 423 | 0 | 진행 중 (의심 138) |
| └─ `est_archivist_5_key.csv` | 100.0% | 200 / 0 / 200 | 0 | 완료 |
| `expanded_stellaris_traditions_delta__3181487775` | 99.9% | 2,579 / 3 / 2,582 | 10 | 진행 중 (의심 3) |
| └─ `est_modifiers_key.csv` | 99.5% | 421 / 2 / 423 | 0 | 진행 중 (의심 2) |
| └─ `est_misc_key.csv` | 99.9% | 712 / 1 / 713 | 10 | 진행 중 (의심 1) |
| └─ `est_academy_traits_key.csv` | 100.0% | 187 / 0 / 187 | 0 | 완료 |
| └─ `est_archivist_5_key.csv` | 100.0% | 200 / 0 / 200 | 0 | 완료 |
| └─ `est_archivist_adopt_key.csv` | 100.0% | 55 / 0 / 55 | 0 | 완료 |
| └─ `est_concepts_key.csv` | 100.0% | 22 / 0 / 22 | 0 | 완료 |
| └─ `est_traditions_key.csv` | 100.0% | 955 / 0 / 955 | 0 | 완료 |
| └─ `replace/est_replacements_key.csv` | 100.0% | 27 / 0 / 27 | 0 | 완료 |
| `extra_leader_traits__3334925693` | 24.9% | 148 / 447 / 595 | 0 | 진행 중 (의심 447) |
| └─ `ELT_ascension_key.csv` | 0.9% | 3 / 339 / 342 | 0 | 진행 중 (의심 339) |
| └─ `ELT_key.csv` | 57.3% | 145 / 108 / 253 | 0 | 진행 중 (의심 108) |
| `extra_ship_components_next__2648658105` | 100.0% | 5,348 / 0 / 5,348 | 1 | 완료 |
| └─ `esc_buildings_key.csv` | 100.0% | 130 / 0 / 130 | 0 | 완료 |
| └─ `esc_components_required_slots_key.csv` | 100.0% | 760 / 0 / 760 | 0 | 완료 |
| └─ `esc_components_utility_key.csv` | 100.0% | 774 / 0 / 774 | 0 | 완료 |
| └─ `esc_options_key.csv` | 100.0% | 197 / 0 / 197 | 0 | 완료 |
| └─ `esc_other_key.csv` | 100.0% | 206 / 0 / 206 | 1 | 완료 |
| └─ `esc_technologies_key.csv` | 100.0% | 1,041 / 0 / 1,041 | 0 | 완료 |
| └─ `esc_weapons_special_key.csv` | 100.0% | 1,224 / 0 / 1,224 | 0 | 완료 |
| └─ `esc_weapons_standard_key.csv` | 100.0% | 1,016 / 0 / 1,016 | 0 | 완료 |
| `fatal_foundations_story_pack_4_3__2627609414` | 100.0% | 382 / 0 / 382 | 1 | 완료 |
| └─ `fatalf_02_key.csv` | 100.0% | 77 / 0 / 77 | 0 | 완료 |
| └─ `fatalf_03_key.csv` | 100.0% | 8 / 0 / 8 | 0 | 완료 |
| └─ `fatalf_anomalies_key.csv` | 100.0% | 62 / 0 / 62 | 0 | 완료 |
| └─ `fatalf_key.csv` | 100.0% | 93 / 0 / 93 | 0 | 완료 |
| └─ `fatalf_modifiers_key.csv` | 100.0% | 11 / 0 / 11 | 0 | 완료 |
| └─ `fatalf_options_key.csv` | 100.0% | 96 / 0 / 96 | 0 | 완료 |
| └─ `mmc_key.csv` | 100.0% | 24 / 0 / 24 | 1 | 완료 |
| └─ `name_lists/name_lists_fatalf_key.csv` | 100.0% | 11 / 0 / 11 | 0 | 완료 |
| `flags_emblems_and_backgrounds_merged__2811907627` | 100.0% | 38 / 0 / 38 | 0 | 완료 |
| └─ `flags_emblems_merger_key.csv` | 100.0% | 38 / 0 / 38 | 0 | 완료 |
| `full_tiny_outliner__2948301103` | 100.0% | 1 / 0 / 1 | 0 | 완료 |
| └─ `replace/tiny_outliner_key.csv` | 100.0% | 1 / 0 / 1 | 0 | 완료 |
| `gigastructural_engineering_more_4_3__1121692237` | 100.0% | 23,461 / 0 / 23,461 | 110 | 완료 |
| └─ `ehof_crisis_names_key.csv` | 100.0% | 25 / 0 / 25 | 0 | 완료 |
| └─ `ehof_system_names_key.csv` | 100.0% | 411 / 0 / 411 | 0 | 완료 |
| └─ `frameworld_key.csv` | 100.0% | 780 / 0 / 780 | 3 | 완료 |
| └─ `giga_agendas_key.csv` | 100.0% | 4 / 0 / 4 | 0 | 완료 |
| └─ `giga_ai_helper_decisions_key.csv` | 100.0% | 14 / 0 / 14 | 0 | 완료 |
| └─ `giga_ai_savings_key.csv` | 100.0% | 132 / 0 / 132 | 0 | 완료 |
| └─ `giga_alderson_key.csv` | 100.0% | 306 / 0 / 306 | 0 | 완료 |
| └─ `giga_alternate_mega_build_key.csv` | 100.0% | 362 / 0 / 362 | 5 | 완료 |
| └─ `giga_asteroid_industry_key.csv` | 100.0% | 170 / 0 / 170 | 0 | 완료 |
| └─ `giga_big_vat_key.csv` | 100.0% | 152 / 0 / 152 | 1 | 완료 |
| └─ `giga_birch_key.csv` | 100.0% | 1,539 / 0 / 1,539 | 24 | 완료 |
| └─ `giga_blokkatnew_key.csv` | 100.0% | 512 / 0 / 512 | 0 | 완료 |
| └─ `giga_catalyst_key.csv` | 100.0% | 31 / 0 / 31 | 1 | 완료 |
| └─ `giga_colony_key.csv` | 100.0% | 1 / 0 / 1 | 0 | 완료 |
| └─ `giga_concepts_key.csv` | 100.0% | 25 / 0 / 25 | 0 | 완료 |
| └─ `giga_databank_key.csv` | 100.0% | 10 / 0 / 10 | 1 | 완료 |
| └─ `giga_debug_events_key.csv` | 100.0% | 8 / 0 / 8 | 0 | 완료 |
| └─ `giga_debug_key.csv` | 100.0% | 2 / 0 / 2 | 0 | 완료 |
| └─ `giga_deposits_key.csv` | 100.0% | 96 / 0 / 96 | 15 | 완료 |
| └─ `giga_eawaf_key.csv` | 100.0% | 576 / 0 / 576 | 2 | 완료 |
| └─ `giga_economic_modifiers_auto_key.csv` | 100.0% | 2,777 / 0 / 2,777 | 0 | 완료 |
| └─ `giga_economic_modifiers_manual_key.csv` | 100.0% | 57 / 0 / 57 | 0 | 완료 |
| └─ `giga_ehof_functions_key.csv` | 100.0% | 378 / 0 / 378 | 0 | 완료 |
| └─ `giga_ehof_key.csv` | 100.0% | 1,868 / 0 / 1,868 | 4 | 완료 |
| └─ `giga_ehof_modifications_key.csv` | 100.0% | 48 / 0 / 48 | 0 | 완료 |
| └─ `giga_extra_growth_key.csv` | 100.0% | 41 / 0 / 41 | 1 | 완료 |
| └─ `giga_gas_giant_hab_key.csv` | 100.0% | 45 / 0 / 45 | 4 | 완료 |
| └─ `giga_hypersiphon_key.csv` | 100.0% | 225 / 0 / 225 | 1 | 완료 |
| └─ `giga_job_scaling_key.csv` | 100.0% | 15 / 0 / 15 | 21 | 완료 |
| └─ `giga_katzen_names_key.csv` | 100.0% | 262 / 0 / 262 | 0 | 완료 |
| └─ `giga_key.csv` | 100.0% | 10,536 / 0 / 10,536 | 21 | 완료 |
| └─ `giga_maginot_key.csv` | 100.0% | 339 / 0 / 339 | 0 | 완료 |
| └─ `giga_matrioshka_brain_key.csv` | 100.0% | 179 / 0 / 179 | 0 | 완료 |
| └─ `giga_mega_events_key.csv` | 100.0% | 155 / 0 / 155 | 0 | 완료 |
| └─ `giga_mega_names_key.csv` | 100.0% | 249 / 0 / 249 | 0 | 완료 |
| └─ `giga_menu_ui_key.csv` | 100.0% | 128 / 0 / 128 | 0 | 완료 |
| └─ `giga_modifiers_key.csv` | 100.0% | 266 / 0 / 266 | 0 | 완료 |
| └─ `giga_names_key.csv` | 100.0% | 52 / 0 / 52 | 0 | 완료 |
| └─ `giga_orbital_elysium_key.csv` | 100.0% | 119 / 0 / 119 | 0 | 완료 |
| └─ `giga_patreon_blokkats_key.csv` | 100.0% | 33 / 0 / 33 | 0 | 완료 |
| └─ `giga_primitives_key.csv` | 100.0% | 72 / 0 / 72 | 0 | 완료 |
| └─ `giga_qso_key.csv` | 100.0% | 212 / 0 / 212 | 2 | 완료 |
| └─ `giga_situations_key.csv` | 100.0% | 73 / 0 / 73 | 0 | 완료 |
| └─ `giga_tech_overwrites_key.csv` | 100.0% | 8 / 0 / 8 | 0 | 완료 |
| └─ `megalist_key.csv` | 100.0% | 5 / 0 / 5 | 4 | 완료 |
| └─ `random_names/giga_birch_natives_names_key.csv` | 100.0% | 12 / 0 / 12 | 0 | 완료 |
| └─ `replace/from_modifiers_key.csv` | 100.0% | 73 / 0 / 73 | 0 | 완료 |
| └─ `replace/giga_modifiers_replace_key.csv` | 100.0% | 6 / 0 / 6 | 0 | 완료 |
| └─ `replace/giga_replace_key.csv` | 100.0% | 72 / 0 / 72 | 0 | 완료 |
| `government_variety_pack__2806903835` | 100.0% | 3,038 / 0 / 3,038 | 8 | 완료 |
| └─ `lrsk_gvp_key.csv` | 100.0% | 3,032 / 0 / 3,032 | 8 | 완료 |
| └─ `lrsk_gvp_real_loc_key.csv` | 100.0% | 6 / 0 / 6 | 0 | 완료 |
| `hyperlane_master__3667301724` | 99.1% | 224 / 2 / 226 | 0 | 진행 중 (의심 2) |
| └─ `hl_master_key.csv` | 99.1% | 224 / 2 / 226 | 0 | 진행 중 (의심 2) |
| `immortal_leaders_trait__686912554` | 100.0% | 2 / 0 / 2 | 0 | 완료 |
| └─ `ilt_key.csv` | 100.0% | 2 / 0 / 2 | 0 | 완료 |
| `kurogane_2_0__3245080043` | 100.0% | 57 / 0 / 57 | 0 | 완료 |
| └─ `fe_key.csv` | 100.0% | 57 / 0 / 57 | 0 | 완료 |
| `kurosections_expanded__2651345333` | 100.0% | 677 / 0 / 677 | 50 | 완료 |
| └─ `kse_key.csv` | 100.0% | 659 / 0 / 659 | 50 | 완료 |
| └─ `kse_starbase_orbital_ring_buildings_key.csv` | 100.0% | 18 / 0 / 18 | 0 | 완료 |
| `lillian_scarlet_zera_zafe_leader_addon_remake__3757204211` | 100.0% | 27 / 0 / 27 | 0 | 완료 |
| └─ `0_key.csv` | 100.0% | 27 / 0 / 27 | 0 | 완료 |
| `max_leader_level__1320158755` | 100.0% | 2 / 0 / 2 | 0 | 완료 |
| └─ `mll_key.csv` | 100.0% | 2 / 0 / 2 | 0 | 완료 |
| `merged_leader_levels__2123646681` | 100.0% | 6,800 / 0 / 6,800 | 17 | 완료 |
| └─ `als_key.csv` | 100.0% | 869 / 0 / 869 | 10 | 완료 |
| └─ `gle_key.csv` | 100.0% | 1,002 / 0 / 1,002 | 3 | 완료 |
| └─ `rls_key.csv` | 100.0% | 3,571 / 0 / 3,571 | 4 | 완료 |
| └─ `sls_key.csv` | 100.0% | 1,358 / 0 / 1,358 | 0 | 완료 |
| `more_ai_personalities__701432146` | 100.0% | 1,891 / 0 / 1,891 | 0 | 완료 |
| └─ `map_basic_key.csv` | 100.0% | 174 / 0 / 174 | 0 | 완료 |
| └─ `map_dip_messages_key.csv` | 100.0% | 1,717 / 0 / 1,717 | 0 | 완료 |
| `more_events_mod__727000451` | 100.0% | 12,459 / 3 / 12,462 | 162 | 진행 중 (의심 3) |
| └─ `mem_ex_planet_key.csv` | 90.0% | 9 / 1 / 10 | 0 | 진행 중 (의심 1) |
| └─ `mem_scfe_story_pack_key.csv` | 99.2% | 125 / 1 / 126 | 1 | 진행 중 (의심 1) |
| └─ `mem_scfe_nyblax_key.csv` | 99.6% | 228 / 1 / 229 | 0 | 진행 중 (의심 1) |
| └─ `aspmod_key.csv` | 100.0% | 519 / 0 / 519 | 11 | 완료 |
| └─ `mem_abandoned_mecha_key.csv` | 100.0% | 9 / 0 / 9 | 0 | 완료 |
| └─ `mem_accelerated_evolution_key.csv` | 100.0% | 5 / 0 / 5 | 0 | 완료 |
| └─ `mem_aevum_key.csv` | 100.0% | 379 / 0 / 379 | 1 | 완료 |
| └─ `mem_agrarian_key.csv` | 100.0% | 15 / 0 / 15 | 0 | 완료 |
| └─ `mem_albino_crystal_key.csv` | 100.0% | 61 / 0 / 61 | 0 | 완료 |
| └─ `mem_ancestors_grudge_key.csv` | 100.0% | 871 / 0 / 871 | 9 | 완료 |
| └─ `mem_ancient_factory_key.csv` | 100.0% | 7 / 0 / 7 | 0 | 완료 |
| └─ `mem_ancient_graveyard_key.csv` | 100.0% | 9 / 0 / 9 | 0 | 완료 |
| └─ `mem_ancient_robots_key.csv` | 100.0% | 74 / 0 / 74 | 0 | 완료 |
| └─ `mem_ancient_satellite_key.csv` | 100.0% | 11 / 0 / 11 | 0 | 완료 |
| └─ `mem_ark_key.csv` | 100.0% | 48 / 0 / 48 | 0 | 완료 |
| └─ `mem_ashes_key.csv` | 100.0% | 57 / 0 / 57 | 0 | 완료 |
| └─ `mem_asteroid_computer_key.csv` | 100.0% | 8 / 0 / 8 | 0 | 완료 |
| └─ `mem_asteroid_derelict_structure_key.csv` | 100.0% | 29 / 0 / 29 | 0 | 완료 |
| └─ `mem_asteroid_structure_key.csv` | 100.0% | 8 / 0 / 8 | 0 | 완료 |
| └─ `mem_astral_tales_key.csv` | 100.0% | 36 / 0 / 36 | 0 | 완료 |
| └─ `mem_beached_key.csv` | 100.0% | 28 / 0 / 28 | 2 | 완료 |
| └─ `mem_black_hole_1_key.csv` | 100.0% | 20 / 0 / 20 | 0 | 완료 |
| └─ `mem_blacksite_key.csv` | 100.0% | 185 / 0 / 185 | 4 | 완료 |
| └─ `mem_boiling_planet_key.csv` | 100.0% | 7 / 0 / 7 | 0 | 완료 |
| └─ `mem_borehole_key.csv` | 100.0% | 27 / 0 / 27 | 0 | 완료 |
| └─ `mem_brainworm_key.csv` | 100.0% | 53 / 0 / 53 | 0 | 완료 |
| └─ `mem_broken_clock_key.csv` | 100.0% | 52 / 0 / 52 | 1 | 완료 |
| └─ `mem_broken_clock_new_key.csv` | 100.0% | 2 / 0 / 2 | 0 | 완료 |
| └─ `mem_caretakers_key.csv` | 100.0% | 6 / 0 / 6 | 0 | 완료 |
| └─ `mem_catacombs_key.csv` | 100.0% | 12 / 0 / 12 | 0 | 완료 |
| └─ `mem_ceaseless_key.csv` | 100.0% | 135 / 0 / 135 | 0 | 완료 |
| └─ `mem_charmak_key.csv` | 100.0% | 17 / 0 / 17 | 1 | 완료 |
| └─ `mem_cliffhanger_key.csv` | 100.0% | 15 / 0 / 15 | 0 | 완료 |
| └─ `mem_cold_key.csv` | 100.0% | 13 / 0 / 13 | 0 | 완료 |
| └─ `mem_colony_ship_key.csv` | 100.0% | 66 / 0 / 66 | 4 | 완료 |
| └─ `mem_comet_lost_key.csv` | 100.0% | 8 / 0 / 8 | 0 | 완료 |
| └─ `mem_command_system_key.csv` | 100.0% | 9 / 0 / 9 | 0 | 완료 |
| └─ `mem_convict_key.csv` | 100.0% | 49 / 0 / 49 | 4 | 완료 |
| └─ `mem_cracked_key.csv` | 100.0% | 29 / 0 / 29 | 0 | 완료 |
| └─ `mem_crashed_object_key.csv` | 100.0% | 11 / 0 / 11 | 0 | 완료 |
| └─ `mem_crawler_key.csv` | 100.0% | 66 / 0 / 66 | 0 | 완료 |
| └─ `mem_crucible_key.csv` | 100.0% | 89 / 0 / 89 | 0 | 완료 |
| └─ `mem_crystal_pyramid_key.csv` | 100.0% | 15 / 0 / 15 | 0 | 완료 |
| └─ `mem_czar_alexei_key.csv` | 100.0% | 86 / 0 / 86 | 0 | 완료 |
| └─ `mem_dead_star_key.csv` | 100.0% | 23 / 0 / 23 | 0 | 완료 |
| └─ `mem_death_world_key.csv` | 100.0% | 186 / 0 / 186 | 0 | 완료 |
| └─ `mem_defying_gravity_key.csv` | 100.0% | 34 / 0 / 34 | 0 | 완료 |
| └─ `mem_demon_ship_key.csv` | 100.0% | 34 / 0 / 34 | 0 | 완료 |
| └─ `mem_descended_key.csv` | 100.0% | 171 / 0 / 171 | 0 | 완료 |
| └─ `mem_dimensional_rift_key.csv` | 100.0% | 23 / 0 / 23 | 0 | 완료 |
| └─ `mem_disguised_planet_key.csv` | 100.0% | 19 / 0 / 19 | 1 | 완료 |
| └─ `mem_diversity_key.csv` | 100.0% | 18 / 0 / 18 | 0 | 완료 |
| └─ `mem_doom_key.csv` | 100.0% | 33 / 0 / 33 | 1 | 완료 |
| └─ `mem_dpe_fe_events_key.csv` | 100.0% | 63 / 0 / 63 | 0 | 완료 |
| └─ `mem_dread_pirate_key.csv` | 100.0% | 95 / 0 / 95 | 3 | 완료 |
| └─ `mem_duel_ritual_key.csv` | 100.0% | 55 / 0 / 55 | 0 | 완료 |
| └─ `mem_dwarf_fortress_key.csv` | 100.0% | 51 / 0 / 51 | 0 | 완료 |
| └─ `mem_eager_traders_key.csv` | 100.0% | 28 / 0 / 28 | 0 | 완료 |
| └─ `mem_eager_traders_modifiers_key.csv` | 100.0% | 12 / 0 / 12 | 0 | 완료 |
| └─ `mem_eden_protocol_key.csv` | 100.0% | 170 / 0 / 170 | 1 | 완료 |
| └─ `mem_elusive_carcosa_key.csv` | 100.0% | 93 / 0 / 93 | 0 | 완료 |
| └─ `mem_engineered_wildlife_key.csv` | 100.0% | 11 / 0 / 11 | 0 | 완료 |
| └─ `mem_enterprise_fallen_key.csv` | 100.0% | 24 / 0 / 24 | 0 | 완료 |
| └─ `mem_extinct_abductors_1_key.csv` | 100.0% | 143 / 0 / 143 | 1 | 완료 |
| └─ `mem_flight_recorder_key.csv` | 100.0% | 9 / 0 / 9 | 0 | 완료 |
| └─ `mem_food_constructor_key.csv` | 100.0% | 158 / 0 / 158 | 2 | 완료 |
| └─ `mem_foss_sky_key.csv` | 100.0% | 14 / 0 / 14 | 0 | 완료 |
| └─ `mem_gaia_troubles_key.csv` | 100.0% | 51 / 0 / 51 | 0 | 완료 |
| └─ `mem_giant_tank_key.csv` | 100.0% | 23 / 0 / 23 | 0 | 완료 |
| └─ `mem_hidden_tundra_key.csv` | 100.0% | 9 / 0 / 9 | 0 | 완료 |
| └─ `mem_hithere_key.csv` | 100.0% | 32 / 0 / 32 | 0 | 완료 |
| └─ `mem_hive_encounter_key.csv` | 100.0% | 54 / 0 / 54 | 0 | 완료 |
| └─ `mem_hollow_asteroid_key.csv` | 100.0% | 85 / 0 / 85 | 1 | 완료 |
| └─ `mem_imperialist_intimidation_key.csv` | 100.0% | 11 / 0 / 11 | 0 | 완료 |
| └─ `mem_imperialist_intimidation_modifiers_key.csv` | 100.0% | 8 / 0 / 8 | 0 | 완료 |
| └─ `mem_into_the_woods_key.csv` | 100.0% | 28 / 0 / 28 | 0 | 완료 |
| └─ `mem_june_19_anomalies_key.csv` | 100.0% | 8 / 0 / 8 | 0 | 완료 |
| └─ `mem_kay_sites_key.csv` | 100.0% | 126 / 0 / 126 | 0 | 완료 |
| └─ `mem_key.csv` | 100.0% | 82 / 0 / 82 | 0 | 완료 |
| └─ `mem_last_orila_key.csv` | 100.0% | 91 / 0 / 91 | 0 | 완료 |
| └─ `mem_left_for_dead_key.csv` | 100.0% | 44 / 0 / 44 | 0 | 완료 |
| └─ `mem_living_asteroid_key.csv` | 100.0% | 6 / 0 / 6 | 0 | 완료 |
| └─ `mem_llayids_key.csv` | 100.0% | 46 / 0 / 46 | 0 | 완료 |
| └─ `mem_lost_emperor_key.csv` | 100.0% | 237 / 0 / 237 | 4 | 완료 |
| └─ `mem_lost_robot_key.csv` | 100.0% | 43 / 0 / 43 | 0 | 완료 |
| └─ `mem_lost_zoo_key.csv` | 100.0% | 11 / 0 / 11 | 0 | 완료 |
| └─ `mem_lotc_key.csv` | 100.0% | 162 / 0 / 162 | 0 | 완료 |
| └─ `mem_lunar_age_key.csv` | 100.0% | 152 / 0 / 152 | 0 | 완료 |
| └─ `mem_lunar_gate_key.csv` | 100.0% | 42 / 0 / 42 | 0 | 완료 |
| └─ `mem_lunatics_key.csv` | 100.0% | 15 / 0 / 15 | 0 | 완료 |
| └─ `mem_matrix_key.csv` | 100.0% | 18 / 0 / 18 | 0 | 완료 |
| └─ `mem_maze_key.csv` | 100.0% | 89 / 0 / 89 | 0 | 완료 |
| └─ `mem_metal_demon_key.csv` | 100.0% | 70 / 0 / 70 | 0 | 완료 |
| └─ `mem_misc_slocs_key.csv` | 100.0% | 89 / 0 / 89 | 0 | 완료 |
| └─ `mem_modifiers_key.csv` | 100.0% | 16 / 0 / 16 | 0 | 완료 |
| └─ `mem_molten_core_key.csv` | 100.0% | 8 / 0 / 8 | 0 | 완료 |
| └─ `mem_mortis_key.csv` | 100.0% | 214 / 0 / 214 | 2 | 완료 |
| └─ `mem_mountain_key.csv` | 100.0% | 72 / 0 / 72 | 2 | 완료 |
| └─ `mem_music_tour_key.csv` | 100.0% | 20 / 0 / 20 | 0 | 완료 |
| └─ `mem_music_tour_modifiers_key.csv` | 100.0% | 14 / 0 / 14 | 0 | 완료 |
| └─ `mem_mysterious_pyramids_key.csv` | 100.0% | 12 / 0 / 12 | 0 | 완료 |
| └─ `mem_names_key.csv` | 100.0% | 360 / 0 / 360 | 0 | 완료 |
| └─ `mem_nanobot_room_key.csv` | 100.0% | 12 / 0 / 12 | 0 | 완료 |
| └─ `mem_native_problem_key.csv` | 100.0% | 25 / 0 / 25 | 0 | 완료 |
| └─ `mem_near_miss_key.csv` | 100.0% | 21 / 0 / 21 | 0 | 완료 |
| └─ `mem_options_key.csv` | 100.0% | 105 / 0 / 105 | 1 | 완료 |
| └─ `mem_origins_key.csv` | 100.0% | 24 / 0 / 24 | 0 | 완료 |
| └─ `mem_orila_primitives_key.csv` | 100.0% | 112 / 0 / 112 | 0 | 완료 |
| └─ `mem_orila_ships_key.csv` | 100.0% | 96 / 0 / 96 | 0 | 완료 |
| └─ `mem_outsiders_key.csv` | 100.0% | 45 / 0 / 45 | 0 | 완료 |
| └─ `mem_paradise_worlds_key.csv` | 100.0% | 2 / 0 / 2 | 0 | 완료 |
| └─ `mem_pi_writing_key.csv` | 100.0% | 3 / 0 / 3 | 0 | 완료 |
| └─ `mem_pioneer_key.csv` | 100.0% | 19 / 0 / 19 | 0 | 완료 |
| └─ `mem_planet_classes_key.csv` | 100.0% | 4 / 0 / 4 | 0 | 완료 |
| └─ `mem_planetary_shields_key.csv` | 100.0% | 18 / 0 / 18 | 0 | 완료 |
| └─ `mem_planetophage_key.csv` | 100.0% | 41 / 0 / 41 | 0 | 완료 |
| └─ `mem_plants_vs_zombies_key.csv` | 100.0% | 21 / 0 / 21 | 0 | 완료 |
| └─ `mem_poisoned_world_key.csv` | 100.0% | 12 / 0 / 12 | 0 | 완료 |
| └─ `mem_pov_key.csv` | 100.0% | 356 / 0 / 356 | 0 | 완료 |
| └─ `mem_premature_ageing_key.csv` | 100.0% | 24 / 0 / 24 | 0 | 완료 |
| └─ `mem_primitive_buildings_key.csv` | 100.0% | 47 / 0 / 47 | 0 | 완료 |
| └─ `mem_primitive_civil_war_key.csv` | 100.0% | 15 / 0 / 15 | 0 | 완료 |
| └─ `mem_primitives_key.csv` | 100.0% | 75 / 0 / 75 | 0 | 완료 |
| └─ `mem_rebel_yell_key.csv` | 100.0% | 65 / 0 / 65 | 9 | 완료 |
| └─ `mem_refuel_key.csv` | 100.0% | 18 / 0 / 18 | 0 | 완료 |
| └─ `mem_rock_brain_key.csv` | 100.0% | 49 / 0 / 49 | 0 | 완료 |
| └─ `mem_rogue_drone_key.csv` | 100.0% | 51 / 0 / 51 | 0 | 완료 |
| └─ `mem_rubicon_key.csv` | 100.0% | 69 / 0 / 69 | 24 | 완료 |
| └─ `mem_sadrell_key.csv` | 100.0% | 213 / 0 / 213 | 8 | 완료 |
| └─ `mem_satellite_cloud_key.csv` | 100.0% | 29 / 0 / 29 | 0 | 완료 |
| └─ `mem_scfe_anomalies_key.csv` | 100.0% | 26 / 0 / 26 | 0 | 완료 |
| └─ `mem_scfe_celestial_disturbance_key.csv` | 100.0% | 53 / 0 / 53 | 0 | 완료 |
| └─ `mem_scfe_key.csv` | 100.0% | 424 / 0 / 424 | 0 | 완료 |
| └─ `mem_scfe_roots_key.csv` | 100.0% | 93 / 0 / 93 | 1 | 완료 |
| └─ `mem_scfe_specimens_key.csv` | 100.0% | 3 / 0 / 3 | 0 | 완료 |
| └─ `mem_scfe_strangeworlds_key.csv` | 100.0% | 138 / 0 / 138 | 0 | 완료 |
| └─ `mem_scfe_ziaskehorn_key.csv` | 100.0% | 34 / 0 / 34 | 0 | 완료 |
| └─ `mem_science_convention_key.csv` | 100.0% | 58 / 0 / 58 | 0 | 완료 |
| └─ `mem_sentinel_key.csv` | 100.0% | 17 / 0 / 17 | 1 | 완료 |
| └─ `mem_severance_key.csv` | 100.0% | 61 / 0 / 61 | 3 | 완료 |
| └─ `mem_shapes_under_ice_key.csv` | 100.0% | 16 / 0 / 16 | 0 | 완료 |
| └─ `mem_ship_size_cap_key.csv` | 100.0% | 55 / 0 / 55 | 0 | 완료 |
| └─ `mem_ships_key.csv` | 100.0% | 42 / 0 / 42 | 0 | 완료 |
| └─ `mem_sight_unseen_key.csv` | 100.0% | 108 / 0 / 108 | 0 | 완료 |
| └─ `mem_sleepers_key.csv` | 100.0% | 96 / 0 / 96 | 0 | 완료 |
| └─ `mem_snowed_in_key.csv` | 100.0% | 62 / 0 / 62 | 0 | 완료 |
| └─ `mem_solar_riches_key.csv` | 100.0% | 8 / 0 / 8 | 0 | 완료 |
| └─ `mem_space_monster_attacks_key.csv` | 100.0% | 130 / 0 / 130 | 0 | 완료 |
| └─ `mem_space_race_key.csv` | 100.0% | 78 / 0 / 78 | 6 | 완료 |
| └─ `mem_specimens_key.csv` | 100.0% | 30 / 0 / 30 | 0 | 완료 |
| └─ `mem_spiritualists_pilgrimage_key.csv` | 100.0% | 70 / 0 / 70 | 0 | 완료 |
| └─ `mem_spiritualists_pilgrimage_modifiers_key.csv` | 100.0% | 7 / 0 / 7 | 0 | 완료 |
| └─ `mem_splinter_colony_key.csv` | 100.0% | 21 / 0 / 21 | 0 | 완료 |
| └─ `mem_star_colors_key.csv` | 100.0% | 6 / 0 / 6 | 0 | 완료 |
| └─ `mem_star_survey_chains_key.csv` | 100.0% | 3 / 0 / 3 | 0 | 완료 |
| └─ `mem_star_survey_key.csv` | 100.0% | 24 / 0 / 24 | 0 | 완료 |
| └─ `mem_star_survey_modifiers_key.csv` | 100.0% | 4 / 0 / 4 | 0 | 완료 |
| └─ `mem_star_survey_projects_key.csv` | 100.0% | 8 / 0 / 8 | 0 | 완료 |
| └─ `mem_starfighter_key.csv` | 100.0% | 21 / 0 / 21 | 0 | 완료 |
| └─ `mem_starship_graveyard_key.csv` | 100.0% | 12 / 0 / 12 | 0 | 완료 |
| └─ `mem_stuck_in_glacier_key.csv` | 100.0% | 66 / 0 / 66 | 0 | 완료 |
| └─ `mem_subspace_beacon_key.csv` | 100.0% | 13 / 0 / 13 | 0 | 완료 |
| └─ `mem_surveyor_key.csv` | 100.0% | 419 / 0 / 419 | 18 | 완료 |
| └─ `mem_synthetic_sun_key.csv` | 100.0% | 47 / 0 / 47 | 0 | 완료 |
| └─ `mem_tales_of_yore_key.csv` | 100.0% | 22 / 0 / 22 | 0 | 완료 |
| └─ `mem_test_events_key.csv` | 100.0% | 56 / 0 / 56 | 0 | 완료 |
| └─ `mem_the_ancient_signal_key.csv` | 100.0% | 22 / 0 / 22 | 0 | 완료 |
| └─ `mem_through_the_fog_key.csv` | 100.0% | 11 / 0 / 11 | 0 | 완료 |
| └─ `mem_towers_key.csv` | 100.0% | 41 / 0 / 41 | 0 | 완료 |
| └─ `mem_under_blanket_key.csv` | 100.0% | 72 / 0 / 72 | 0 | 완료 |
| └─ `mem_vazuran_event_system_key.csv` | 100.0% | 31 / 0 / 31 | 0 | 완료 |
| └─ `mem_vazuran_menace_key.csv` | 100.0% | 447 / 0 / 447 | 30 | 완료 |
| └─ `mem_version_check_key.csv` | 100.0% | 2 / 0 / 2 | 0 | 완료 |
| └─ `mem_vestigial_wormhole_key.csv` | 100.0% | 67 / 0 / 67 | 3 | 완료 |
| └─ `mem_viral_engine_key.csv` | 100.0% | 74 / 0 / 74 | 0 | 완료 |
| └─ `mem_visitor_key.csv` | 100.0% | 125 / 0 / 125 | 0 | 완료 |
| └─ `mem_voggo_key.csv` | 100.0% | 25 / 0 / 25 | 0 | 완료 |
| └─ `mem_wargames_key.csv` | 100.0% | 25 / 0 / 25 | 0 | 완료 |
| └─ `mem_we_are_gods_key.csv` | 100.0% | 5 / 0 / 5 | 0 | 완료 |
| └─ `mem_wpdr_key.csv` | 100.0% | 22 / 0 / 22 | 2 | 완료 |
| └─ `name_lists/name_list_ORILA_key.csv` | 100.0% | 265 / 0 / 265 | 0 | 완료 |
| `more_leader_traits__3195070547` | 100.0% | 629 / 0 / 629 | 0 | 완료 |
| └─ `mlt_hydra_key.csv` | 100.0% | 605 / 0 / 605 | 0 | 완료 |
| └─ `mlt_hydra_new_traits_key.csv` | 100.0% | 24 / 0 / 24 | 0 | 완료 |
| `nsc3_season_1__683230077` | 100.0% | 1,572 / 0 / 1,572 | 26 | 완료 |
| └─ `name_lists/name_list_1-NSC-Steve_key.csv` | 100.0% | 1 / 0 / 1 | 0 | 완료 |
| └─ `nsc_behaviors_key.csv` | 100.0% | 44 / 0 / 44 | 0 | 완료 |
| └─ `nsc_components_key.csv` | 100.0% | 375 / 0 / 375 | 0 | 완료 |
| └─ `nsc_events_key.csv` | 100.0% | 51 / 0 / 51 | 0 | 완료 |
| └─ `nsc_jobs_key.csv` | 100.0% | 14 / 0 / 14 | 0 | 완료 |
| └─ `nsc_megastructures_key.csv` | 100.0% | 96 / 0 / 96 | 0 | 완료 |
| └─ `nsc_modifiers_key.csv` | 100.0% | 69 / 0 / 69 | 0 | 완료 |
| └─ `nsc_mothball_key.csv` | 100.0% | 47 / 0 / 47 | 0 | 완료 |
| └─ `nsc_namelists_key.csv` | 100.0% | 15 / 0 / 15 | 0 | 완료 |
| └─ `nsc_perks_key.csv` | 100.0% | 3 / 0 / 3 | 0 | 완료 |
| └─ `nsc_policies_edicts_key.csv` | 100.0% | 137 / 0 / 137 | 0 | 완료 |
| └─ `nsc_ship_browser_key.csv` | 100.0% | 6 / 0 / 6 | 0 | 완료 |
| └─ `nsc_shipsections_key.csv` | 100.0% | 322 / 0 / 322 | 0 | 완료 |
| └─ `nsc_starbase_key.csv` | 100.0% | 140 / 0 / 140 | 0 | 완료 |
| └─ `nsc_technologies_key.csv` | 100.0% | 201 / 0 / 201 | 26 | 완료 |
| └─ `nsc_tooltips_key.csv` | 100.0% | 36 / 0 / 36 | 0 | 완료 |
| └─ `replace/nsc_replacements_key.csv` | 100.0% | 15 / 0 / 15 | 0 | 완료 |
| `otter_editor__1595999824` | 100.0% | 383 / 0 / 383 | 7 | 완료 |
| └─ `ottereditor_key.csv` | 100.0% | 275 / 0 / 275 | 7 | 완료 |
| └─ `otterleader_key.csv` | 100.0% | 108 / 0 / 108 | 0 | 완료 |
| `otter_editor_s_dynamic_mod_menu_add_on__2460698354` | 100.0% | 3 / 0 / 3 | 0 | 완료 |
| └─ `otterdmm_key.csv` | 100.0% | 3 / 0 / 3 | 0 | 완료 |
| `planetary_diversity__819148835` | 100.0% | 1,856 / 0 / 1,856 | 0 | 완료 |
| └─ `planetarydiversity_ascension_worlds_key.csv` | 100.0% | 116 / 0 / 116 | 0 | 완료 |
| └─ `planetarydiversity_domed_colonies_key.csv` | 100.0% | 211 / 0 / 211 | 0 | 완료 |
| └─ `planetarydiversity_engine_events_key.csv` | 100.0% | 138 / 0 / 138 | 0 | 완료 |
| └─ `planetarydiversity_key.csv` | 100.0% | 197 / 0 / 197 | 0 | 완료 |
| └─ `planetarydiversity_more_arcs_key.csv` | 100.0% | 48 / 0 / 48 | 0 | 완료 |
| └─ `planetarydiversity_planet_classes_key.csv` | 100.0% | 823 / 0 / 823 | 0 | 완료 |
| └─ `planetarydiversity_planet_modifiers_key.csv` | 100.0% | 313 / 0 / 313 | 0 | 완료 |
| └─ `planetarydiversity_start_screen_message_key.csv` | 100.0% | 9 / 0 / 9 | 0 | 완료 |
| └─ `planetarydiversity_vanilla_overwrites_key.csv` | 100.0% | 1 / 0 / 1 | 0 | 완료 |
| `plentiful_traditions_4_2_x__1311725711` | 100.0% | 1,627 / 0 / 1,627 | 40 | 완료 |
| └─ `plentiful_traditions_key.csv` | 100.0% | 1,627 / 0 / 1,627 | 40 | 완료 |
| `psionic_species_expansion__2461999384` | 100.0% | 1,626 / 0 / 1,626 | 10 | 완료 |
| └─ `pse_key.csv` | 100.0% | 1,626 / 0 / 1,626 | 10 | 완료 |
| `scripted_trigger_undercoat__2868680633` | 100.0% | 240 / 0 / 240 | 9 | 완료 |
| └─ `event_icon_tooltips_key.csv` | 100.0% | 207 / 0 / 207 | 0 | 완료 |
| └─ `undercoat_key.csv` | 100.0% | 33 / 0 / 33 | 9 | 완료 |
| `sins_of_the_prophets_stellaris__751394361` | 100.0% | 78 / 0 / 78 | 0 | 완료 |
| └─ `sotp_key.csv` | 100.0% | 78 / 0 / 78 | 0 | 완료 |
| `starbase_extended_3_0__3250900527` | 100.0% | 173 / 0 / 173 | 1 | 완료 |
| └─ `starbase_extended_3.0_key.csv` | 100.0% | 173 / 0 / 173 | 1 | 완료 |
| `stellaris_101_how_to_read__2819720352` | 100.0% | 781 / 0 / 781 | 0 | 완료 |
| └─ `dontsub_key.csv` | 100.0% | 781 / 0 / 781 | 0 | 완료 |
| `stellaris_v4_3_general_fixes__3701747681` | 100.0% | 157 / 0 / 157 | 0 | 완료 |
| └─ `ariphaos_patch_key.csv` | 100.0% | 60 / 0 / 60 | 0 | 완료 |
| └─ `ariphaos_patch_resolution_modifiers_key.csv` | 100.0% | 12 / 0 / 12 | 0 | 완료 |
| └─ `dux_key.csv` | 100.0% | 26 / 0 / 26 | 0 | 완료 |
| └─ `marauder_addition_key.csv` | 100.0% | 4 / 0 / 4 | 0 | 완료 |
| └─ `replace/astral_planes_fix_key.csv` | 100.0% | 1 / 0 / 1 | 0 | 완료 |
| └─ `replace/dux_replace_key.csv` | 100.0% | 16 / 0 / 16 | 0 | 완료 |
| └─ `replace/extreme_frontiers_fix_key.csv` | 100.0% | 1 / 0 / 1 | 0 | 완료 |
| └─ `replace/federations_fix_key.csv` | 100.0% | 5 / 0 / 5 | 0 | 완료 |
| └─ `replace/infernal_fix_key.csv` | 100.0% | 2 / 0 / 2 | 0 | 완료 |
| └─ `replace/projects_fix_key.csv` | 100.0% | 1 / 0 / 1 | 0 | 완료 |
| └─ `replace/prospectoriumr_resource_discovery_fix_key.csv` | 100.0% | 5 / 0 / 5 | 0 | 완료 |
| └─ `replace/psionic_traditions_fix_key.csv` | 100.0% | 1 / 0 / 1 | 0 | 완료 |
| └─ `replace/zzzz_yyyy_key.csv` | 100.0% | 7 / 0 / 7 | 0 | 완료 |
| └─ `unplugged_fix_key.csv` | 100.0% | 2 / 0 / 2 | 0 | 완료 |
| └─ `vfix_missing_keys_key.csv` | 100.0% | 14 / 0 / 14 | 0 | 완료 |
| `the_merger_of_rules_3_14_4_3_label_fix__2807759164` | 100.0% | 15 / 0 / 15 | 6 | 완료 |
| └─ `! merg_event_key.csv` | 100.0% | 14 / 0 / 14 | 0 | 완료 |
| └─ `! merg_key.csv` | 100.0% | 1 / 0 / 1 | 6 | 완료 |
| `trait_diversity__1928831043` | 100.0% | 641 / 0 / 641 | 0 | 완료 |
| └─ `traitdiversity_key.csv` | 100.0% | 641 / 0 / 641 | 0 | 완료 |
| `trait_point_traits__3170396896` | 100.0% | 89 / 0 / 89 | 0 | 완료 |
| └─ `exptr_traits_key.csv` | 100.0% | 89 / 0 / 89 | 0 | 완료 |
| `ui_overhaul_dynamic__1623423360` | 100.0% | 48 / 0 / 48 | 0 | 완료 |
| └─ `ui_overhaul_qhd_key.csv` | 100.0% | 48 / 0 / 48 | 0 | 완료 |
| `ui_overhaul_dynamic_ascension_slots__1890399946` | 100.0% | 23 / 0 / 23 | 0 | 완료 |
| └─ `ui_overhaul_qhd-technology_key.csv` | 100.0% | 23 / 0 / 23 | 0 | 완료 |
| `ui_overhaul_dynamic_extended_topbar_for_dlcs__3090328185` | 100.0% | 1 / 0 / 1 | 0 | 완료 |
| └─ `ui_overhaul_qhd_dlc_key.csv` | 100.0% | 1 / 0 / 1 | 0 | 완료 |
| `ui_overhaul_dynamic_planetary_diversity__1623423504` | 100.0% | 1 / 0 / 1 | 0 | 완료 |
| └─ `ui_overhaul_qhd-planetary_diversity_key.csv` | 100.0% | 1 / 0 / 1 | 0 | 완료 |
| `ui_overhaul_dynamic_speeddial__1649442597` | 100.0% | 51 / 0 / 51 | 1 | 완료 |
| └─ `speeddial-uiod_key.csv` | 100.0% | 11 / 0 / 11 | 0 | 완료 |
| └─ `speeddial_key.csv` | 100.0% | 40 / 0 / 40 | 1 | 완료 |
| `ultimate_imperium_of_man_namelist__1651768817` | 100.0% | 1 / 0 / 1 | 0 | 완료 |
| └─ `iom_key.csv` | 100.0% | 1 / 0 / 1 | 0 | 완료 |
| `unique_ascension_perks_4_3_dev_branch__2811428998` | 100.0% | 5,286 / 0 / 5,286 | 357 | 완료 |
| └─ `anomalies_respawn_key.csv` | 100.0% | 156 / 0 / 156 | 10 | 완료 |
| └─ `constructible_l-gate_key.csv` | 100.0% | 24 / 0 / 24 | 0 | 완료 |
| └─ `l-cluster_access_key.csv` | 100.0% | 41 / 0 / 41 | 0 | 완료 |
| └─ `leng_uap_key.csv` | 100.0% | 55 / 0 / 55 | 0 | 완료 |
| └─ `regentmaker_key.csv` | 100.0% | 135 / 0 / 135 | 0 | 완료 |
| └─ `replace/defender_of_the_galaxy_key.csv` | 100.0% | 2 / 0 / 2 | 0 | 완료 |
| └─ `special_project_extended_key.csv` | 100.0% | 1,173 / 0 / 1,173 | 65 | 완료 |
| └─ `uap_event_patch_key.csv` | 100.0% | 437 / 0 / 437 | 0 | 완료 |
| └─ `unique_ascension_perks_key.csv` | 100.0% | 3,263 / 0 / 3,263 | 282 | 완료 |
