-- Migration 018: USGS hydrogeologic region descriptions lookup
-- Short factual descriptions for display in the Groundwater Context section of the report.

CREATE TABLE IF NOT EXISTS usgs_hydrogeologic_region_descriptions (
    reg_code    TEXT PRIMARY KEY,
    description TEXT NOT NULL,
    confidence  TEXT NOT NULL DEFAULT 'high'  -- 'high' or 'review'
);

-- ─── Principal Aquifers (57) ─────────────────────────────────────────────────

INSERT INTO usgs_hydrogeologic_region_descriptions (reg_code, description, confidence) VALUES

  ('N300ADAVMS',
   'Pennsylvanian sandstone in central Oklahoma yields moderate groundwater for rural and municipal use; water quality is generally good with locally elevated iron.',
   'high'),

  ('N400ABKSMP',
   'Fractured Ordovician carbonates in southern Oklahoma yield prolific springs and wells through karst conduits; sinkholes and rapid contaminant transport are significant site risks.',
   'high'),

  ('N100BSNRGB',
   'Alluvial sand and gravel fill southwestern desert basins yielding moderate to high volumes; water tables are often very deep in arid intermontane settings.',
   'high'),

  ('N400BSNRGC',
   'Fractured and karstified limestone in the Basin and Range province yields variable supplies; springs are common but water tables may be very deep in arid areas.',
   'high'),

  ('N400BISCYN',
   'Highly porous Pleistocene limestone in southeast Florida yields very high volumes; the aquifer is very shallow and highly vulnerable to saltwater intrusion.',
   'high'),

  ('N400BLAINE',
   'Permian gypsum and dolomite in western Oklahoma yield modest groundwater but are prone to dissolution, creating subsidence and sinkhole risks at the surface.',
   'high'),

  ('N100CACSTL',
   'Alluvial sand and gravel in southern California coastal basins yield high volumes but face saltwater intrusion risk where heavily pumped near the coast.',
   'high'),

  ('S300CAMORD',
   'Deep Cambrian-Ordovician sandstones beneath the upper Midwest yield high artesian volumes under confined pressure; wells commonly exceed 300 feet in depth.',
   'high'),

  ('N400CSLHYN',
   'Eocene limestone in the North Carolina coastal plain yields high volumes for municipal and industrial use; saltwater intrusion risk increases near the coast.',
   'high'),

  ('N300CNRLOK',
   'Permian sandstone and minor limestone in central Oklahoma yield moderate groundwater; salinity can be elevated at depth in some parts of the aquifer.',
   'high'),

  ('S100CNRLVL',
   'Thick alluvial sand and gravel beneath California''s Central Valley yields very high volumes; intensive pumping has caused significant land subsidence in parts of the valley.',
   'high'),

  ('S100CSLLWD',
   'Thick Cenozoic sands along the Gulf Coast yield large volumes from multiple water-bearing zones; saltwater intrusion and land subsidence are documented risks.',
   'high'),

  ('N300COPLTS',
   'Mesozoic sandstones of the Colorado Plateau yield confined and unconfined supplies; water tables are often very deep in this arid, canyon-carved region.',
   'high'),

  ('N600CMBPLV',
   'Highly permeable basaltic lava flows across the Columbia Plateau yield very high volumes supporting large irrigation and municipal supplies throughout eastern Washington and Oregon.',
   'high'),

  ('N100CMBPLB',
   'Alluvial and glaciofluvial sand and gravel in Columbia Plateau basins yield moderate to high volumes, often hydraulically connected to the underlying basalt aquifer.',
   'high'),

  ('S300DNVRBS',
   'Cretaceous and Paleocene sandstones beneath the Denver Basin yield moderate water from deep confined wells; water levels are declining in heavily pumped areas.',
   'high'),

  ('N300ERLMZC',
   'Triassic sandstones and fractured basalts in East Coast Mesozoic rift basins yield variable groundwater; well productivity depends heavily on fracture intersections.',
   'high'),

  ('S500EDRTRN',
   'Cretaceous limestone and dolomite in central Texas form a major karst aquifer with high-yield springs; the system is highly vulnerable to surface contamination.',
   'high'),

  ('S400FLORDN',
   'Thick Eocene to Oligocene carbonates across Florida and adjacent states form one of the world''s most productive aquifers; karst features pose significant sinkhole risk.',
   'high'),

  ('N100HGHPLN',
   'Sand, gravel, and caliche of the Ogallala Formation yield very high irrigation volumes across the central Great Plains; water levels have declined significantly in parts of Kansas and Texas.',
   'high'),

  ('N300JCBSVL',
   'Precambrian Jacobsville sandstone in the Upper Michigan Peninsula yields moderate volumes of high-quality groundwater for municipal and domestic supply.',
   'high'),

  ('N300LCRTCS',
   'Lower Cretaceous sandstones including the Dakota Formation provide confined artesian water across the northern Great Plains; wells are deep and yields vary by location.',
   'high'),

  ('N300LTRTRY',
   'Paleocene and Eocene sandstones in the Williston Basin and northern Great Plains yield moderate water; elevated salinity is common at depth in many areas.',
   'high'),

  ('N300MRSHLL',
   'Mississippian-age sandstone in lower Michigan provides moderate to high yields of good-quality water for municipal, industrial, and domestic supply.',
   'high'),

  ('N100MSRVVL',
   'Holocene and Pleistocene sand and gravel beneath the Mississippi River valley yield very high volumes from shallow depths for agricultural and municipal supply.',
   'high'),

  ('S100MSEMBM',
   'Cretaceous to Quaternary sands beneath the Mississippi Embayment provide high-yield confined water; artesian pressure is common in deeper units heavily used for municipal supply.',
   'high'),

  ('N500MSSPPI',
   'Mississippian limestone, dolomite, and sandstone across the mid-continent yield variable groundwater; carbonate units may exhibit karst features and associated sinkhole risk.',
   'high'),

  ('N400NYNECB',
   'Cambrian and Ordovician carbonate rocks in New York and New England yield variable groundwater through fractures and local karst; sinkholes are possible in limestone terrain.',
   'high'),

  ('N300NYSDSN',
   'Devonian sandstone and shale in southwestern New York yield low to moderate groundwater, typically supporting domestic and rural water supply.',
   'high'),

  ('S100NATLCP',
   'Cretaceous and Tertiary sands of the Northern Atlantic Coastal Plain form a multilayer system yielding high volumes; saltwater threatens coastal and deep production zones.',
   'high'),

  ('S100NRMTIB',
   'Quaternary alluvial and glaciofluvial sand and gravel in Northern Rocky Mountain basins yield moderate to high volumes for irrigation and domestic use.',
   'high'),

  ('N400ORDVCN',
   'Ordovician dolomite and limestone in the mid-continent yield moderate groundwater through fractures; elevated mineralization can reduce water quality at depth.',
   'high'),

  ('S400OZRKPL',
   'Karst and fractured Paleozoic carbonates in the Ozark Plateau yield very high volumes; sinkholes and rapid contaminant migration are significant development concerns.',
   'high'),

  ('N100PCFNWV',
   'Fractured and permeable basalt flows in the Pacific Northwest yield variable groundwater; yields are highest in rubbly flow contacts and lowest in dense lava interiors.',
   'high'),

  ('N100PCFNWB',
   'Glaciofluvial and alluvial sand and gravel in Pacific Northwest lowland basins yield moderate to high volumes for municipal and domestic supply.',
   'high'),

  ('N500PLOZOC',
   'An assemblage of Paleozoic sandstones and carbonate rocks in the central interior yields variable groundwater; productivity depends strongly on local stratigraphy and structure.',
   'high'),

  ('N100PCSRVR',
   'Shallow alluvial sand and gravel along the Pecos River yield limited groundwater; water quality is often poor due to high salinity from adjacent evaporite dissolution.',
   'high'),

  ('N300PNSLVN',
   'Pennsylvanian sandstone and coal-bearing sequences in the mid-continent yield low to moderate groundwater; iron and sulfate can affect water quality.',
   'high'),

  ('N400PDMBRC',
   'Metamorphic carbonate rocks in the Piedmont and Blue Ridge yield variable groundwater through fractures and local karst; variable well yields and sinkholes are common.',
   'high'),

  ('N400PDMBRX',
   'Fractured igneous and metamorphic rocks in the Piedmont and Blue Ridge yield modest water through weathered saprolite and fractures; well productivity is highly variable.',
   'high'),

  ('S100PGTSND',
   'Glacial outwash and interglacial sand and gravel deposits in the Puget Sound lowland yield high volumes for municipal and domestic supply across western Washington.',
   'high'),

  ('S100RIOGRD',
   'Thick sand and gravel fill the Rio Grande rift valley yielding moderate to high volumes; water tables can be deep near Albuquerque and water quality varies by location.',
   'high'),

  ('S400RSWLBS',
   'Permian carbonate rocks in southeastern New Mexico form a karst aquifer with artesian conditions in confined zones; springs and wells support irrigation in the Roswell area.',
   'high'),

  ('N300RSHSPG',
   'Permian Rush Springs and Quartermaster sandstones in western Oklahoma yield moderate groundwater for municipal and rural use; water quality is generally good.',
   'high'),

  ('N100SYMOUR',
   'Quaternary fluvial sand and gravel along river terraces in north-central Texas yield variable unconfined groundwater susceptible to drought-related water-level declines.',
   'high'),

  ('N400SLRDVN',
   'Silurian and Devonian carbonate rocks in the Great Lakes region yield moderate to high groundwater through fractures; sinkholes and karst are a known risk in dolomite terrain.',
   'high'),

  ('N600SKRVPV',
   'Young basaltic lava flows of the Snake River Plain form one of the most productive volcanic aquifers in the US, yielding extremely high volumes for large-scale irrigation.',
   'high'),

  ('N600SKRVPB',
   'Alluvial and lacustrine sand and gravel at the Snake River Plain margins yield moderate groundwater, typically less productive than the adjacent basalt aquifer.',
   'high'),

  ('S100SECSLP',
   'Cretaceous and Tertiary sands and carbonates along the southeastern coastal plain yield high groundwater from multiple zones; saltwater intrusion affects coastal areas.',
   'high'),

  ('N600SRNVDV',
   'Fractured Tertiary volcanic tuffs and lavas in southern Nevada yield limited to moderate groundwater; deep water tables are common in this very arid region.',
   'high'),

  ('S100SURFCL',
   'Shallow Pliocene to Holocene sand and shell deposits across Florida yield moderate groundwater but are unconfined and highly vulnerable to surface contamination.',
   'high'),

  ('S100TXCLUP',
   'Eocene to Miocene sands and clays in the South Texas coastal plain yield moderate groundwater; salinity increases toward the Gulf Coast and with depth.',
   'high'),

  ('N300UPCTCS',
   'Upper Cretaceous sandstones in the northern Great Plains provide confined artesian water; well yields are moderate and water quality can include elevated iron or sulfate at depth.',
   'high'),

  ('N300WYTRTR',
   'Oligocene and Miocene sandstones in Wyoming and adjacent states yield moderate groundwater in intermontane basins; elevated dissolved solids are present in some units.',
   'high'),

  ('N400UPCRBN',
   'Silurian dolomite underlying the upper Midwest yields moderate to high groundwater through fractures and dissolution; localized karst and sinkhole risk are present.',
   'high'),

  ('N500VLYRDG',
   'Folded Paleozoic sandstones and carbonates yield variable groundwater; carbonate units carry karst and sinkhole risk while sandstone yields depend on fracturing.',
   'high'),

  ('N100WLMLWD',
   'Alluvial and glaciofluvial sand and gravel in the Willamette Valley yield moderate to high groundwater supporting municipal and agricultural supply near Portland and Salem.',
   'high'),

-- ─── Secondary Hydrogeologic Regions (69) ────────────────────────────────────

  ('SHR53ADIRONMTNS',
   'Fractured Precambrian crystalline rocks in the Adirondacks yield low to moderate groundwater; well productivity is unpredictable and depends heavily on fracture intersections.',
   'high'),

  ('SHR50ARCHGLAC',
   'Glacially modified sedimentary terrain yields variable groundwater; glacial deposits overlying bedrock sandstones and shales are typically the most productive zones.',
   'high'),

  ('SHR38ARCHUNGLAC',
   'Unglaciated sedimentary terrain of interbedded sandstones and shales yields variable groundwater; water tables can be deep in erosionally dissected uplands.',
   'high'),

  ('SHR13BNRHGHL',
   'Elevated mountain blocks of mixed igneous, metamorphic, and sedimentary rock yield limited groundwater through fractures; springs supply local domestic needs.',
   'high'),

  ('SHR28BLACKHILLS',
   'Paleozoic and Mesozoic sedimentary rocks ringing the Black Hills yield variable groundwater; artesian conditions exist in some confined sandstone units.',
   'high'),

  ('SHR27BLACKHILLX',
   'The Precambrian crystalline core of the Black Hills yields low groundwater volumes through fractures; wells are typically shallow and used for domestic and ranch supply.',
   'high'),

  ('SHR12BLUEMTNS',
   'Mixed volcanic, sedimentary, and crystalline rocks in the Blue Mountains of northeastern Oregon yield variable groundwater; basaltic flows are the most productive units where present.',
   'high'),

  ('SHR47CANSHIELD',
   'Ancient Precambrian crystalline rocks of the Canadian Shield yield very limited groundwater through fractures; wells are low-yielding and highly dependent on fracture intersections.',
   'high'),

  ('SHR61CAPECODIS',
   'Crystalline bedrock underlies glacial deposits in this region; productive wells draw from glacial sand and gravel rather than the low-yield fractured bedrock.',
   'high'),

  ('SHR59CHAMPVS',
   'Ordovician and Cambrian sedimentary rocks in the Champlain and Hudson valleys yield moderate groundwater; alluvial valley fills provide higher local yields.',
   'high'),

  ('SHR58CHAMPVX',
   'Crystalline rocks in the Champlain-Hudson region yield limited groundwater through fractures; well productivity is variable and depends on depth and fracture orientation.',
   'high'),

  ('SHR08COASTRNGES',
   'Folded and faulted Tertiary sedimentary rocks in California''s Coast Ranges yield variable groundwater; valley alluvium provides higher yields than the deformed bedrock.',
   'high'),

  ('SHR32ENEWMEX',
   'Permian and Cretaceous sedimentary rocks in eastern New Mexico yield variable groundwater; evaporite dissolution can impair water quality with elevated sulfate and chloride.',
   'high'),

  ('SHR45EDTRINKT',
   'Cretaceous limestone and dolomite yield moderate to high groundwater through fractures and karst; contamination can travel very rapidly through carbonate conduits.',
   'high'),

  ('SHR69FLORQ',
   'Quaternary carbonate and clastic deposits yield shallow unconfined groundwater in Florida; the zone is highly vulnerable to contamination and saltwater intrusion near the coast.',
   'high'),

  ('SHR68FLORT',
   'Tertiary carbonate rocks yield high groundwater as part of the Floridan aquifer system; karst features and sinkholes are common surface development concerns.',
   'high'),

  ('SHR29FONTRNGE',
   'Cretaceous and Tertiary sedimentary rocks along Colorado''s Front Range yield variable groundwater; fractured formations near the mountain front can support municipal and domestic wells.',
   'high'),

  ('SHR14GRNDCANY',
   'Ancient Paleozoic and Proterozoic sedimentary rocks in the Grand Canyon region yield limited to moderate groundwater at considerable depth; springs emerge at major stratigraphic contacts.',
   'high'),

  ('SHR66GULFCOAT',
   'Tertiary sands and clays along the Gulf Coastal Plain yield moderate to high groundwater from multiple horizons; saltwater intrusion and land subsidence are known risks.',
   'high'),

  ('SHR56IAMOPA',
   'Pennsylvanian shales, limestones, and sandstones in Iowa and Missouri yield modest groundwater from shallow unconfined units susceptible to drought and contamination.',
   'high'),

  ('SHR57ILLBASN',
   'Paleozoic sedimentary rocks in the Illinois Basin yield moderate groundwater from sandstone and carbonate units; deeper rocks commonly contain saline water unsuitable for potable use.',
   'high'),

  ('SHR52INRMIBASN',
   'Deep Paleozoic sedimentary rocks in the central Michigan Basin contain mostly saline water at depth; most usable supply comes from overlying glacial deposits.',
   'high'),

  ('SHR34INTERPA',
   'Pennsylvanian sandstone, shale, and limestone in the interior mid-continent yield low to moderate groundwater; coal-bearing strata can affect water quality.',
   'high'),

  ('SHR33INTERP',
   'Permian sandstone, dolomite, and evaporite in the interior basin yield variable groundwater; evaporite dissolution elevates sulfate and chloride concentrations in some areas.',
   'high'),

  ('SHR07KLAMATH',
   'Deeply eroded igneous and metamorphic rocks of the Klamath Mountains yield low to moderate groundwater through fractures; springs are locally important in this rugged terrain.',
   'high'),

  ('SHR44LLANO',
   'Precambrian crystalline and Paleozoic carbonate rocks of the Llano Uplift in central Texas yield limited to moderate groundwater; the hard crystalline core is poorly productive.',
   'high'),

  ('SHR06MSCASCADE',
   'Young Cascade volcanic rocks yield variable groundwater through permeable lava flows; springs and streams are sustained by high-elevation snowmelt recharge.',
   'high'),

  ('SHR05MIDCASCADE',
   'Pliocene and Pleistocene basalt flows in the middle Cascades yield moderate to high groundwater; springs and streams receive substantial recharge from seasonal snowmelt.',
   'high'),

  ('SHR22MIDROCKS',
   'Mesozoic and Cenozoic sedimentary rocks in Middle Rocky Mountain basins yield variable groundwater; basin-fill alluvium in intermontane valleys is most productive.',
   'high'),

  ('SHR23MIDROCKV',
   'Tertiary volcanic rocks in the Middle Rockies yield moderate groundwater through permeable flows and tuffaceous deposits; yields vary considerably with local volcanic stratigraphy.',
   'high'),

  ('SHR21MIDROCKX',
   'Precambrian and Paleozoic crystalline rocks forming Middle Rocky Mountain cores yield very limited groundwater through fractures; well yields are typically low.',
   'high'),

  ('SHR65MISSEMBAYKT',
   'Cretaceous to Tertiary sands and clays in the Mississippi Embayment yield high groundwater under artesian conditions; deep confined units are heavily used for municipal supply.',
   'high'),

  ('SHR55NEKSPPA',
   'Pennsylvanian and Permian sedimentary rocks in Nebraska and Kansas yield low to moderate groundwater; alluvial valley deposits are more productive than consolidated bedrock.',
   'high'),

  ('SHR49NCENTRALPZ',
   'Paleozoic carbonates and sandstones beneath glacial deposits in the north-central interior yield moderate groundwater, often accessed through the overlying glacial cover.',
   'high'),

  ('SHR48NCENTRALX',
   'Precambrian crystalline rocks near the Canadian Shield yield very limited groundwater through fractures; glacial deposits are the primary water supply source in this region.',
   'high'),

  ('SHR54NAPPBASNPZ',
   'Devonian and Pennsylvanian sandstones in the northern Appalachian Basin yield low to moderate groundwater; iron and methane from shales can affect water quality.',
   'high'),

  ('SHR60NAPPMTNSX',
   'Crystalline metamorphic and igneous rocks in the northern Appalachians yield limited groundwater through weathered saprolite and fractures; well productivity is highly variable.',
   'high'),

  ('SHR04NCASCADE',
   'Precambrian to Mesozoic crystalline rocks in the North Cascades yield very limited groundwater through fractures; springs and perched zones supply local domestic needs.',
   'high'),

  ('SHR20NROCKQ',
   'Quaternary glacial and alluvial deposits in Northern Rocky Mountain valleys yield moderate to high groundwater, forming the primary productive aquifer in many highland basins.',
   'high'),

  ('SHR18NROCKS',
   'Cretaceous and Paleozoic sedimentary rocks in the Northern Rockies yield variable groundwater from sandstone and carbonate units; artesian conditions exist in some confined formations.',
   'high'),

  ('SHR19NROCKV',
   'Tertiary basalts and rhyolites in the Northern Rockies yield variable groundwater; permeable lava flows provide higher yields than dense welded tuffs.',
   'high'),

  ('SHR17NROCKX',
   'Precambrian crystalline and metamorphic rocks forming Northern Rocky Mountain cores yield very limited groundwater through fractures; domestic well yields are generally low.',
   'high'),

  ('SHR35OKPERMPA',
   'Pennsylvanian and Permian sandstones, limestones, and shales in Oklahoma yield low to moderate groundwater; several named sandstone units provide important local rural supplies.',
   'high'),

  ('SHR63OUACHITA',
   'Tightly folded Paleozoic sandstones and shales in the Ouachita Mountains yield low to moderate groundwater through fractures; springs along fold structures provide local supply.',
   'high'),

  ('SHR51OUTMIBASN',
   'Silurian and Devonian carbonate and sandstone rocks at the Michigan Basin margin yield moderate groundwater; dissolution features in carbonate units create local karst conditions.',
   'high'),

  ('SHR36OZARKSPZ',
   'Paleozoic carbonate and sandstone of the Ozark Plateau yield variable to high groundwater through fractures and karst; sinkhole risk and rapid contaminant migration are elevated.',
   'high'),

  ('SHR37OZARKSX',
   'Precambrian crystalline rock exposed in the St. Francois Mountains yields very limited groundwater through fractures; surrounding Paleozoic sedimentary rocks are far more productive.',
   'high'),

  ('SHR11PACNWVOL',
   'Basaltic and andesitic volcanic rocks in the Pacific Northwest yield variable to high groundwater through permeable lava flow contacts; yields diminish in older, more-altered rock.',
   'high'),

  ('SHR31RATON',
   'Cretaceous and Tertiary sedimentary rocks in the Raton Basin of northern New Mexico and Colorado yield moderate groundwater; coal seams and gas-bearing formations are present.',
   'high'),

  ('SHR16RIOGNDHGHL',
   'Tertiary volcanic rocks flanking the Rio Grande rift yield limited to moderate groundwater through fractures and permeable flow units; springs are locally important.',
   'high'),

  ('SHR09SIERRAS',
   'Mesozoic granitic rocks of the Sierra Nevada yield very limited groundwater through fractures; productive wells are typically sited in valley alluvium along range-front streams.',
   'high'),

  ('SHR67SECOASTPLT',
   'Tertiary sands and carbonates along the southeastern coastal plain yield moderate to high groundwater from multiple zones; saltwater intrusion is a concern in coastal areas.',
   'high'),

  ('SHR10SOCAL',
   'Mixed granitic, metamorphic, and sedimentary rocks in the Transverse and Peninsular Ranges yield limited bedrock groundwater; productive supply comes from alluvial valley fills.',
   'high'),

  ('SHR25SROCKS',
   'Mesozoic and Cenozoic sedimentary rocks in Southern Rocky Mountain basins yield variable groundwater; intermontane basin fills are more productive than consolidated bedrock.',
   'high'),

  ('SHR26SROCKV',
   'Tertiary volcanic rocks in the Southern Rockies including the San Juan volcanic field yield variable groundwater; permeable basalt flows provide higher yields than rhyolitic tuffs.',
   'high'),

  ('SHR24SROCKX',
   'Precambrian crystalline rocks forming Southern Rocky Mountain cores yield very limited groundwater through fractures; well yields are typically low and unpredictable.',
   'high'),

  ('SHR40TXK',
   'Cretaceous limestone and chalk in Texas yield variable groundwater; carbonate units can produce karst features and sinkholes while chalks and marls yield limited water.',
   'high'),

  ('SHR64TXKT',
   'Cretaceous to Tertiary sedimentary rocks in Texas yield variable groundwater; deeper units can be saline and karst features occur in some Cretaceous limestone formations.',
   'high'),

  ('SHR41TXPA',
   'Pennsylvanian limestone, shale, and sandstone in north-central Texas yield low to moderate groundwater; shallow unconfined units are susceptible to drought depletion.',
   'high'),

  ('SHR39TXTR',
   'Triassic Dockum Group redbeds in Texas yield limited and often saline groundwater; this formation is not a reliable primary water supply for site development.',
   'high'),

  ('SHR46UPKGLAC',
   'Upper Cretaceous shales and sandstones beneath glacial till in the northern plains yield modest groundwater; overlying glacial deposits are often a more productive source.',
   'high'),

  ('SHR30UPKUNGLAC',
   'Upper Cretaceous sandstones and shales in unglaciated areas of the northern plains yield limited groundwater; artesian conditions exist in some confined sand units.',
   'high'),

  ('SHR01WAORCOASTS',
   'Eocene to Miocene sedimentary rocks along the WA-OR coast ranges yield variable groundwater through fractures and interbedded sands; valley alluvium provides higher local yields.',
   'high'),

  ('SHR02WAORCOASTV',
   'Eocene and younger volcanic rocks along the Pacific coast ranges yield moderate groundwater through fractured and permeable basalt; younger flows are generally more productive.',
   'high'),

  ('SHR42WTXS',
   'Permian sedimentary rocks in west Texas include evaporites that impair groundwater quality with high sulfate and chloride; freshwater supply is limited and often at great depth.',
   'high'),

  ('SHR43WTXV',
   'Tertiary volcanic rocks in the Trans-Pecos region of west Texas yield limited groundwater through fractures; well yields are typically low in this very arid terrain.',
   'high'),

-- ─── Gap-filling regions (confidence = 'review') ─────────────────────────────

  ('SHR15XCOPLATS',
   'Gap-filling region approximating Colorado Plateau settings; Mesozoic sandstones and shales yield variable groundwater, often at significant depth in this arid region.',
   'review'),

  ('SHR03PUGET',
   'Gap-filling region approximating Puget Sound lowland settings; glacial and interglacial sedimentary deposits yield moderate to high groundwater in stratified drift sequences.',
   'review'),

  ('SHR62XVLYRDG',
   'Gap-filling region approximating Valley and Ridge settings; folded Paleozoic carbonates and sandstones yield variable groundwater, with karst risk in limestone and dolostone units.',
   'review');

-- 126 rows total
