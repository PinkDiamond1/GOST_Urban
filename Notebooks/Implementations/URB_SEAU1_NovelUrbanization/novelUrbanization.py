import sys, os, importlib, shutil, multiprocessing
import requests
import rasterio, elevation, richdem
import rasterio.warp
from rasterio import features

import pandas as pd
import geopandas as gpd
import numpy as np

from shapely.geometry import MultiPolygon, Polygon, box, Point

#Import raster helpers
import GOSTRocks.rasterMisc as rMisc
from GOSTRocks.misc import tPrint

#Import GOST urban functions
sys.path.append("../../src")
import GOST_Urban.UrbanRaster as urban
import GOST_Urban.urban_helper as helper

importlib.reload(helper)
importlib.reload(rMisc)

def calculate_urban(iso3, inG, inG2, pop_files, ea_file, output_folder, km=True, small=True, include_ghsl_h20=True, evaluate=True):   
    global_landcover  = "/home/public/Data/GLOBAL/LANDCOVER/GLOBCOVER/2015/ESACCI-LC-L4-LCCS-Map-300m-P1Y-2015-v2.0.7.tif"
    global_ghspop = "/home/public/Data/GLOBAL/Population/GHS/250/GHS_POP_E2015_GLOBE_R2019A_54009_250_V1_0.tif"
    global_ghspop_1k = "/home/public/Data/GLOBAL/Population/GHS/GHS_POP_E2015_GLOBE_R2019A_54009_1K_V1_0.tif"
    global_ghbuilt = "/home/public/Data/GLOBAL/URBAN/GHS/GHS_1K_BUILT/GHS_BUILT_LDS2014_GLOBE_R2018A_54009_1K_V1_0.tif"
    global_dem_1k = "/home/public/Data/GLOBAL/ELEV/noaa_1km.tif"
    ghs_smod = "/home/public/Data/GLOBAL/URBAN/GHS/GHS_SMOD/GHS_SMOD_POP2015_GLOBE_R2019A_54009_1K_V2_0.tif"
    ghsl_vrt = "/home/public/Data/GLOBAL/GHSL/ghsl.vrt"

    admin2_250_stats = os.path.join(output_folder, f"{iso3}_URBAN_ADMIN2_STATS_COMPILED.csv")
    commune_250_stats = os.path.join(output_folder, f"{iso3}_URBAN_COMMUNE_STATS_COMPILED.csv")
    admin2_1k_stats = os.path.join(output_folder, f"{iso3}_URBAN_ADMIN2_STATS_COMPILED_1k.csv")
    commune_1k_stats = os.path.join(output_folder, f"{iso3}_URBAN_COMMUNE_STATS_COMPILED_1k.csv")
    
    inD = inG.loc[inG['ISO3'] == iso3]
    inD['geometry'] = inD['geometry'].apply(lambda x: x.buffer(500))
    inD = inD.to_crs('epsg:4326')
    
    inD2 = inG2.loc[inG2['ISO3'] == iso3]
    inD2 = inD2.to_crs('epsg:4326')  
    
    ### Process 1km data
    if km:
        xx = helper.urban_country(iso3, output_folder, inD, pop_files,
                                final_folder="FINAL_STANDARD_1KM", ghspop_suffix="1k")
        adm2_res = os.path.join(xx.final_folder, "URBAN_ADMIN2_STATS_COMPILED.csv") 
        ea_res   = os.path.join(xx.final_folder, "URBAN_COMMUNE_STATS_COMPILED.csv")
        tPrint(f"{iso3} ***1k Extracting Global Layers")
        xx.extract_layers(global_landcover, global_ghspop, global_ghspop_1k, global_ghbuilt, ghsl_vrt, ghs_smod)
        tPrint(f"{iso3} ***1k Downloading and processing elevation")
        xx.process_dem(global_dem=global_dem_1k)
        tPrint(f"{iso3} ***1k Standardizing rasters")
        xx.standardize_rasters(include_ghsl_h20)
        tPrint(f"{iso3} ***1k Calculating Urban")
        xx.calculate_urban()
        tPrint(f"{iso3} ***1k Calculating Zonal admin2")
        if not os.path.exists(admin2_1k_stats):
            zonal_adm2 = xx.pop_zonal_admin(inD2)
            zonal_adm2.to_csv(admin2_1k_stats)
            tPrint(f"{iso3} ***1k Calculating Zonal communes")         
            if os.path.exists(ea_file):
                inEA = gpd.read_file(ea_file)
                zonal_ea = xx.pop_zonal_admin(inEA)
                zonal_ea.to_csv(commune_1k_stats)
        if evaluate:
            tPrint(f"{iso3} ***1k Evaluating Data")
            xx.evaluateOutput(admin2_1k_stats, commune_1k_stats)        
    
    ### Process 250m data 
    if small:
        xx = helper.urban_country(iso3, output_folder, inD, pop_files)
        tPrint(f"{iso3} ***** Extracting Global Layers %s" % iso3)
        xx.extract_layers(global_landcover, global_ghspop, global_ghspop_1k, global_ghbuilt, ghsl_vrt, ghs_smod)
        tPrint(f"{iso3} ***** Downloading and processing elevation %s" % iso3)
        xx.process_dem(global_dem=global_dem_1k)
        tPrint(f"{iso3} ***** Standardizing rasters")
        xx.standardize_rasters(include_ghsl_h20)
        tPrint(f"{iso3} ***** Calculating Urban")
        xx.calculate_urban()
        tPrint(f"{iso3} ***** Calculating Zonal admin2")
        if not os.path.exists(admin2_250_stats):
            zonal_adm2 = xx.pop_zonal_admin(inD2)
            zonal_adm2.to_csv(admin2_250_stats)
            tPrint(f"{iso3} ***** Calculating Zonal communes")                   
            if os.path.exists(ea_file):            
                inEA = gpd.read_file(ea_file)
                zonal_ea = xx.pop_zonal_admin(inEA)
                zonal_ea.to_csv(commune_250_stats)
        if evaluate:
            tPrint(f"{iso3} ***** Evaluating Data")
            xx.evaluateOutput(admin2_250_stats, commune_250_stats)
        
                
def calc_pp_urban(in_folder, default_pop_file, admin_layer, output_folder, iso3=''):
    ''' Summarize urbanization from Pierre-Philippe's Dartboard methodology
    
    INPUT
        input_folder [string path] - location of dartboard urbanization
        default_pop_file [string path] - default pop filename to use for urban population calculations 
        admin_layer [string path] - zones used to summarize population
    RETURN
        [geopandas dataframe] - contains total population and urban population for each shape
    '''
    urban_layers = [os.path.join(in_folder, x) for x in os.listdir(in_folder) if x[-4:] == ".tif"]
    if iso3 != '':
        urban_layers = [x for x in urban_layers if iso3.lower() in x]
    
    cur_layer = urban_layers[0]
    inD = gpd.read_file(admin_layer)
    default_pop_1k = default_pop_file.replace(default_pop_file[:3], "%s1k" % default_pop_file[:3])
    for cur_layer in urban_layers:
        #tPrint(cur_layer)
        #Open and read in urban data
        urban_r = rasterio.open(cur_layer)
        urban_data = urban_r.read()
        urban_data = (urban_data > 0).astype(urban_r.meta['dtype'])
        #Extract population data
        urban_layer = os.path.basename(cur_layer)  
        default_pop = default_pop_file
        
        if "1k" in urban_layer:
            default_pop = default_pop_1k
            pop_layer = os.path.basename(cur_layer)[:11]
            pop_folder = os.path.join(output_folder, "FINAL_STANDARD_1KM")
        else:
            pop_layer = os.path.basename(cur_layer)[:9]
            pop_folder = os.path.join(output_folder, "FINAL_STANDARD")
        pop_file = os.path.join(pop_folder,"%s.tif" % pop_layer)
        
        if not os.path.exists(pop_file):            
            if "1k" in urban_layer:
                default_pop = default_pop_1k
                pop_layer = os.path.basename(cur_layer)[:9]
                pop_folder = os.path.join(output_folder, "FINAL_STANDARD_1KM")
            else:
                pop_layer = os.path.basename(cur_layer)[:7]
                pop_folder = os.path.join(output_folder, "FINAL_STANDARD")
            pop_file = os.path.join(pop_folder,"%s.tif" % pop_layer)
        
        pop_r = rasterio.open(pop_file)
        pop_data = pop_r.read()
        pop_data = pop_data * urban_data
        meta = urban_r.meta.copy()
        meta.update(dtype = pop_data.dtype)
        
        #Calculate total population
        total_pop_field = os.path.basename(pop_file).replace(".tif", "")
        if not total_pop_field in inD.columns:
            res = rMisc.zonalStats(inD, pop_r, reProj=True, minVal=0)
            res = pd.DataFrame(res, columns=['SUM', 'MIN', 'MAX', 'MEAN'])
            inD[total_pop_field] = res['SUM']
        
        #Calculate urban population
        with rMisc.create_rasterio_inmemory(meta, pop_data) as pop_r:
            res = rMisc.zonalStats(inD, pop_r, reProj=True, minVal=0)
            res = pd.DataFrame(res, columns=['SUM', 'MIN', 'MAX', 'MEAN'])
            
        inD[os.path.basename(cur_layer).replace(".tif","")] = res['SUM']
    return(inD)

def check_no_data(in_folder):
    ''' loop through all the tif files in the FINAL folders and calculate the number of no-data cells
    '''
    for root, dirs, files in os.walk(in_folder):
        if "FINAL" in root:
            for f in files:
                if (not "NO_DATA" in f) and (not 'urban' in f):
                    if f[-4:] == ".tif":
                        cur_file = os.path.join(root, f)
                        curR = rasterio.open(cur_file)
                        curD = curR.read()
                        print(f'{f}: {(curD == curR.meta["nodata"]).sum()}')
                              
def pp_point_urban_summaries(inD, urban_tiffs, out_file):
    ''' summarize urbanization for point locations (inD) for each urban definition file (urban_tiffs)
    '''
    for pFile in urban_tiffs:
        if pFile.endswith(".tif"):
            try:
                rFile = rasterio.open(pFile)
                if inD.crs != rFile.crs:
                    inD = inD.to_crs(rFile.crs)
                geoms = [(row['geometry'].x, row['geometry'].y) for idx, row in inD.iterrows()]
                urb_res = rFile.sample(geoms)
                inD[os.path.basename(pFile).replace(".tif","")] = [x[0] for x in list(urb_res)]
            except:
                pass
    pd.DataFrame(inD.drop(['geometry'], axis=1)).to_csv(out_file)

                              
def point_urban_summaries(inD, pop_tiffs, out_file):
    ''' summarize urbanization for point locations (inD) for each population file (pop_tiffs)
    '''
    for pFile in pop_tiffs:
        urb_file = pFile.replace(".tif", "_urban.tif")
        hd_file = pFile.replace(".tif", "_urban_hd.tif")
        # For each population file there is an urban file and a HD urban file
        for curFile in [urb_file, hd_file]:
            try:
                inUrb = rasterio.open(curFile)
                if inD.crs!= inUrb.crs:
                    inD = inD.to_crs(inUrb.crs)
                geoms = [(row['geometry'].x, row['geometry'].y) for idx, row in inD.iterrows()]
                urb_res = inUrb.sample(geoms)
                inD[os.path.basename(curFile).replace(".tif","")] = [x[0] for x in list(urb_res)]
            except:
                pass
    pd.DataFrame(inD.drop(['geometry'], axis=1)).to_csv(out_file)
    
def run_country(iso3):
    local_path = "/home/public/Data/COUNTRY/{country}/POPULATION/WORLDPOP/".format(country=iso3)

def run_zonal(iso3, output_folder, inG, pop_files, ea_file, pt_file):
    ''' Summarize zonal statistics for urbanization numbers against polygons and points for both WB and PP urban calculations
    '''
    pp_deleniations_folder = "/home/wb411133/data/Projects/MR_Novel_Urbanization/Data/AAPPC/Delineations"
    
    inD = inG.loc[inG['ISO3'] == iso3].copy()
    inD['geometry'] = inD['geometry'].apply(lambda x: x.buffer(500))
    inD = inD.to_crs('epsg:4326')
    
    # Run zonal stats on WB stats using ea boundary
    out_ea_zonal = os.path.join(output_folder, f"{iso3}_EA_WB_URBAN_1K.csv")
    if not os.path.exists(out_ea_zonal) & os.path.exists(ea_file):
        xx = helper.urban_country(iso3, output_folder, inD, pop_files, final_folder="FINAL_STANDARD_1KM", ghspop_suffix="1k")
        zonal_ea = xx.pop_zonal_admin(gpd.read_file(ea_file))
        zonal_ea.to_csv(out_ea_zonal)

        out_ea_zonal = os.path.join(output_folder, f"{iso3}_EA_WB_URBAN_250.csv")
        xx = helper.urban_country(iso3, output_folder, inD, pop_files, final_folder="FINAL_STANDARD", ghspop_suffix="")
        zonal_ea = xx.pop_zonal_admin(gpd.read_file(ea_file))
        zonal_ea.to_csv(out_ea_zonal)
    
    # Run zonal stats on pp urban using ea boundary
    out_ea_pp_zonal = os.path.join(output_folder, f"{iso3}_EA_PP_URBAN.csv")
    if (os.path.exists(ea_file)): # & not os.path.exists(out_ea_pp_zonal):
        pp_zonal_ea = calc_pp_urban(pp_deleniations_folder, pop_files[0][1], ea_file, output_folder, iso3)
        if 'geometry' in pp_zonal_ea.columns:
            pp_zonal_ea = pp_zonal_ea.drop(['geometry'], axis=1)
        pp_zonal_ea.to_csv(out_ea_pp_zonal)
    
    wb_out_file = os.path.join(output_folder, f"{iso3}_HH_GPS_WB_URBAN.csv")
    pp_out_file = os.path.join(output_folder, f"{iso3}_HH_GPS_PP_URBAN.csv")    
    if os.path.exists(pt_file) and not os.path.exists(wb_out_file):
        cur_pt = gpd.read_file(pt_file)                
        all_tiffs = []
        base_folder = os.path.join(output_folder, "FINAL_STANDARD")
        base_folder_1km = os.path.join(output_folder, "FINAL_STANDARD_1KM")
        for file_defs in pop_files:
            pFile = file_defs[1]
            all_tiffs.append(os.path.join(base_folder, pFile))
            all_tiffs.append(os.path.join(base_folder_1km, pFile.replace(f"{iso3.lower()}", f"{iso3.lower()}1k")))    
        point_urban_summaries(cur_pt, all_tiffs, wb_out_file)
        
    if os.path.exists(pt_file) and not os.path.exists(pp_out_file):
        # Get list of urban tiffs from PP
        urban_tiffs = [os.path.join(pp_deleniations_folder, x) for x in os.listdir(pp_deleniations_folder) if iso3.lower() in x]
        pp_point_urban_summaries(cur_pt, urban_tiffs, pp_out_file)
        
    
EA_DEFS = { # Define ea files per iso3
    # iso3 : folder, polygon file, point file
    "BFA": ["/home/wb411133/data/Projects/MR_Novel_Urbanization/Data/EA_Files/BurkinaFaso/","bfa_admbnda_adm3_igb_20200323.shp", "bfa.geojson"],
    "TCD": ["/home/wb411133/data/Projects/MR_Novel_Urbanization/Data/EA_Files/Chad", "tcd_a_admbnd_adm3_ocha.shp", "ChadFinal.geojson"],
    "GIN": ["/home/wb411133/data/Projects/MR_Novel_Urbanization/Data/EA_Files/Guinea/","gin_admbnda_adm3_ocha.shp", "GINFinal.geojson"],
    "GNB": ["/home/wb411133/data/Projects/MR_Novel_Urbanization/Data/EA_Files/Guinea Bissau/","gnb_admbnda_adm2_1m_salb_20210609.shp", "GNBFinal.geojson"],
    "GAB": ["/home/wb411133/data/Projects/MR_Novel_Urbanization/Data/EA_Files/Gabon", "CANTONS_region.shp", "gabon_gps.geojson"],
    "LSO": ["/home/wb411133/data/Projects/MR_Novel_Urbanization/Data/EA_Files/Lesotho/","lso_admbnda_adm2_FAO_MLGCA_2019.shp", "lesotho_list.geojson"],
    "MWI": ["/home/wb411133/data/Projects/MR_Novel_Urbanization/Data/EA_Files/Malawi", "mwi_admbnda_adm3_nso_20181016.shp", "checkedcoord_malawi.geojson"],
    "MLI": ["/home/wb411133/data/Projects/MR_Novel_Urbanization/Data/EA_Files/Mali", "mli_admbnda_adm3_1m_dnct_20190802.shp", "MaliFinal.geojson"],
    "MAU": ["/home/wb411133/data/Projects/MR_Novel_Urbanization/Data/EA_Files/Mauritania", "MAU_edit.shp", "mauritania.geojson"],
    "NER": ["/home/wb411133/data/Projects/MR_Novel_Urbanization/Data/EA_Files/Niger", "NER_adm03_feb2018.shp", "NigerFinal.geojson"],
    "SEN": ["/home/wb411133/data/Projects/MR_Novel_Urbanization/Data/EA_Files/Senegal/","sen_admbnda_adm3_1m_gov_ocha_20190426.shp", "senegal.geojson"],    
    "UGA": ["/home/wb411133/data/Projects/MR_Novel_Urbanization/Data/EA_Files/Uganda/uganda_parishes_cleaned_attached", "uganda_parishes_cleaned_attached.shp", ""],
    'CIV': ["/home/wb411133/data/Projects/MR_Novel_Urbanization/Data/EA_Files/CIV/", "civ_admbnda_adm1_cntig_ocha_itos_20180706.shp", "civ.geojson"],    
    'AGO': ["/home/wb411133/data/Projects/MR_Novel_Urbanization/Data/EA_Files/Angola/", "bairros.shp", ""],
    'ETH': ["/home/wb411133/data/Projects/MR_Novel_Urbanization/Data/EA_Files/Ethiopia/", "Ethiopia_pti_admin3.shp", "HBS_GPS.geojson"],
}
    
if __name__ == "__main__":
    print("STARTING")
    global_bounds         = "/home/public/Data/GLOBAL/ADMIN/Admin0_Polys.shp"
    global_bounds_adm2    = "/home/public/Data/GLOBAL/ADMIN/Admin2_Polys.shp"
    global_ghspop = "/home/public/Data/GLOBAL/Population/GHS/250/GHS_POP_E2015_GLOBE_R2019A_54009_250_V1_0.tif"
    global_ghspop_1k = "/home/public/Data/GLOBAL/Population/GHS/GHS_POP_E2015_GLOBE_R2019A_54009_1K_V1_0.tif"
    worldPop_2015         = "/home/public/Data/GLOBAL/Population/WorldPop_PPP_2015/worldPop_2015.vrt"
    constrained_WP_folder = "/home/public/Data/GLOBAL/Population/RF_SSA_2015-2020"
    out_base              = "/home/wb411133/data/Projects/MR_Novel_Urbanization/Data"
    
    inG = gpd.read_file(global_bounds)
    inG2 = gpd.read_file(global_bounds_adm2)

    runSmall = True
    runLarge = True
    
    focal_countries = inG.loc[inG['Region'] == 'Sub-Saharan Africa'].sort_values(['ISO3'])['ISO3'].values
    nCores = min(len(focal_countries), round(multiprocessing.cpu_count() * .8))
    all_commands = []
    zonal_commands = []
    for iso3 in EA_DEFS.keys(): #focal_countries: #: #['MAR','DZA','TUN','LBY']
        tPrint(iso3)
        try:
            cur_def = EA_DEFS[iso3]
            ea_file = os.path.join(cur_def[0], cur_def[1])
            pt_file = os.path.join(cur_def[0], cur_def[2])
        except:
            ea_file = ''
            pt_file = ''
            
        output_folder = os.path.join(out_base, "%s_URBAN_DATA_new_naming" % iso3)
        pop_files = [[worldPop_2015, f'{iso3.lower()}_upo15.tif']]
        # Identify the constrained WorldPop layer
        c_WP_15 = f'{constrained_WP_folder}/{iso3}/ppp_{iso3}_const_2015.tif'
        c_WP_20 = f'{constrained_WP_folder}/{iso3}/ppp_{iso3}_const_2020.tif'
        if os.path.exists(c_WP_15):
            pop_files.append([c_WP_15, f'{iso3.lower()}_cpo15.tif'])
        else:
            print(f'***** Could not locate constrained WorldPop 2015 for {iso3}')
        if os.path.exists(c_WP_20):
            pop_files.append([c_WP_20, f'{iso3.lower()}_cpo20.tif'])
        else:
            print(f'***** Could not locate constrained WorldPop 2020 for {iso3}')
        
        '''
        try:
            run_zonal(iso3, output_folder, inG, pop_files, ea_file, pt_file)
            #calculate_urban(iso3, inG, inG2, pop_files, ea_file, output_folder, km=True, small=True)
        except:
            print(f"Error with {iso3}")        
        '''
        cur_args = [iso3, inG, inG2, pop_files, ea_file, output_folder]
        all_commands.append(cur_args)
        
        pop_files.append([constrained_WP_folder, f'{iso3.lower()}_gpo.tif'])               
        zonal_args = [iso3, output_folder, inG, pop_files, ea_file, pt_file]
        zonal_commands.append(zonal_args)
    
    with multiprocessing.Pool(nCores) as pool:
        #pool.starmap(calculate_urban, all_commands)
        pool.starmap(run_zonal, zonal_commands)
    
        
    
    