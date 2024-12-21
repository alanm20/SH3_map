#
# Silent Hill 3 PC Map loader
# alanm1
# v0.1 initial release

#Based on:
# This is a direct port of Murgo's PS2  Silent Hill 3 map import Blender scripts. 
# Original blender plugin can be found in his github side
# https://github.com/Murugo/Misc-Game-Research
# https://github.com/Murugo/Misc-Game-Research/tree/main/PS2/Silent%20Hill%202%2B3/Blender/addons/io_sh2_sh3


MeshScale = 1.0         #Override mesh scale (default is 1.0)
debug = 0                       #Prints debug info (1 = on, 0 = off)

from inc_noesis import *
import math
import glob
import re
import copy
from operator import itemgetter, attrgetter
from collections import deque, namedtuple
from io import *
    
def registerNoesisTypes():
    handle = noesis.register("Silent Hill 3: 3D Map [PC]", ".map")
    noesis.setHandlerTypeCheck(handle, meshCheckType)
    noesis.setHandlerLoadModel(handle, meshLoadModel)

    handle = noesis.register("Silent Hill 3: 2D Texture [PC]", ".dat")
    noesis.setHandlerTypeCheck(handle, rawTexCheckType)
    noesis.setHandlerLoadRGBA(handle, rawTexLoad)
    
    handle = noesis.register("Silent Hill 3: 2D Map Texture [PC]", ".tex")
    noesis.setHandlerTypeCheck(handle, rawMapTexCheckType)
    noesis.setHandlerLoadRGBA(handle, rawMapTexLoad)   
    #noesis.logPopup()
    return 1
    
def rawTexCheckType(data):
    bs = NoeBitStream(data)
    magic = bs.readUInt()
    if magic == 0xFFFFFFFF:
        return 1
    else: 
        print("Unknown file magic: " + str(hex(magic) + " expected 0xFFFFFFFF!"))
        return 0
    
def rawTexLoad(data, texList):
    bs = NoeBitStream(data)
    texStart = bs.tell()
    bs.seek(0x8,NOESEEK_REL)
    ddsWidth = bs.readUShort()
    ddsHeight= bs.readUShort()
    unk = bs.readUInt()
    ddsSize = bs.readUInt()
    dataOffset = bs.readUShort()    
    bs.seek(texStart+dataOffset, NOESEEK_ABS)
    if debug:
        print("rawTexure",ddsWidth,ddsHeight)
    ddsData = bs.readBytes(ddsSize)
    ddsData = rapi.imageDecodeRaw(ddsData, ddsWidth, ddsHeight, "b8g8r8a8")
    ddsFmt = noesis.NOESISTEX_RGBA32
    texList.append(NoeTexture("Texture", ddsWidth, ddsHeight, ddsData, ddsFmt))
    return 1

def rawMapTexCheckType(data):
    bs = NoeBitStream(data)
    magic = bs.readUInt()
    bs.seek(0x20, NOESEEK_ABS)
    magic1 = bs.readUInt()
    if magic == 0xFFFFFFFF and magic1 == 0xFFFFFFFF:
        return 1
    else: 
        print("Unknown file magic: " + str(hex(magic) + " expected 0xFFFFFFFF!"))
        return 0
    
def rawMapTexLoad(data, texList, base_name=""):
    bs = NoeBitStream(data)
    bs.seek(0x14)
    num_tex = bs.readUShort()
    bs.seek(0x20)
    for i in range(num_tex):
        texStart = bs.tell()
        bs.seek(0x8,NOESEEK_REL)
        ddsWidth = bs.readUShort()
        ddsHeight= bs.readUShort()
        unk = bs.readUInt()
        ddsSize = bs.readUInt()
        dataOffset = bs.readUShort()    
        bs.seek(texStart+dataOffset, NOESEEK_ABS)
        if debug:
            print("rawTexure",ddsWidth,ddsHeight)
        tex_name = base_name +"Tex_" + str(i)
        ddsData = bs.readBytes(ddsSize)
        print(tex_name,ddsWidth,ddsHeight, hex(ddsSize))
        ddsData = rapi.imageDecodeRaw(ddsData, ddsWidth, ddsHeight, "b8g8r8a8")
        ddsFmt = noesis.NOESISTEX_RGBA32
        texList.append(NoeTexture(tex_name, ddsWidth, ddsHeight, ddsData, ddsFmt))
    return 1


def meshCheckType(data):
    bs = NoeBitStream(data)
    ### skip extra header
    uiMagic = bs.readUInt();    
    
    if uiMagic == 0xFFFFFFFF:
        return 1      
    else:
        print("Unsupported Mesh header! " + str(uiMagic))
    return 0

def sh3LoadMDLTex(bs, num_tex, texList):
    bs.seek(0x10,NOESEEK_ABS)
    texs_offset = bs.readUInt()
    bs.seek(texs_offset+0x20,NOESEEK_ABS)
    for i in range(num_tex):
        texStart = bs.tell()
        print ("tell ",hex(texStart))
        bs.seek(0x8,NOESEEK_REL)
        ddsWidth = bs.readUShort()
        ddsHeight= bs.readUShort()
        unk = bs.readUInt()
        ddsSize = bs.readUInt()
        dataOffset = bs.readUShort()
        
        bs.seek(texStart+dataOffset, NOESEEK_ABS)

        texName = "Tex_"+str(i)
        if debug:
            print(texName,ddsWidth,ddsHeight)
        print(texName,ddsWidth,ddsHeight,ddsSize)
        ddsData = bs.readBytes(ddsSize)
        ddsData = rapi.imageDecodeRaw(ddsData, ddsWidth, ddsHeight, "b8g8r8a8")
        ddsFmt = noesis.NOESISTEX_RGBA32
        texList.append(NoeTexture(texName, ddsWidth, ddsHeight, ddsData, ddsFmt))
    return 1


class MeshGroupInfo:
  def __init__(self, index):
    self.index = index


class MeshInfo:
  def __init__(self, index, flag, mesh_group_info):
    self.index = index
    self.flag = flag
    self.mesh_group_info = mesh_group_info


class SubmeshInfo:
  def __init__(self, index, mesh_info):
    self.index = index
    self.mesh_info = mesh_info

class meshFile(object):
    
    def __init__(self, data):
        self.inFile = None
        self.texExtension = ""
                
        self.inFile = NoeBitStream(data)

        self.fileSize = int(len(data))
                        
        self.matList = []
        self.texList = []
        self.num_GB_tex = 0
        self.num_TR_tex = 0

    def loadMesh(self):

        filepath = rapi.getInputName()

        self.basename  = os.path.splitext(os.path.basename(filepath))[0]
        dir = os.path.dirname(filepath)
        self.area_name = self.basename[:2]
        
        GB_Tex_fn = os.path.join(dir, self.area_name +"GB.tex")
        TR_Tex_fn = os.path.join(dir,self.basename + "TR.tex")
        print("file name ",filepath, GB_Tex_fn, TR_Tex_fn)
        # load GB and TR tex file if they exist in same directory
        if os.path.exists(GB_Tex_fn):
            with open(GB_Tex_fn,"rb") as file:    
                tlen = len(self.texList)           
                rawMapTexLoad(file.read(), self.texList,"GB_")
                self.num_GB_tex = len(self.texList) - tlen
        if os.path.exists(TR_Tex_fn):
            with open(TR_Tex_fn,"rb") as file:     
                tlen = len(self.texList)                      
                rawMapTexLoad(file.read(), self.texList,"TR_")
                self.num_TR_tex = len(self.texList) - tlen
        
        bs = self.inFile
        ### skip extra header
        bs.seek(0x0c, NOESEEK_ABS)
        mesh_start = bs.readUInt()
        
        bs.seek(0x1c, NOESEEK_ABS)

        mesh_group_offsets = struct.unpack("III",bs.read(12))

        bs.seek(0x44, NOESEEK_ABS)

        self.num_tex = struct.unpack("H",bs.read(2))[0]
        
        if self.num_tex > 0:
            sh3LoadMDLTex( bs, self.num_tex, self.texList)

        bs.seek(mesh_start + 0x20)
        
        self.global_matrix = NoeMat44([struct.unpack("ffff",bs.read(16)) for _ in range(4)]).transpose()

        for offs in sorted(mesh_group_offsets):
            if offs > 0:
                self.parse_mesh_groups(bs, offs)
                break
        return 1

    def parse_mesh_groups(self, f, offs):
        index = 0
        non_MDL_tex = 0
        while offs > 0:
            f.seek(offs, NOESEEK_ABS)
            next_offs, data_start_offs, total_size, _= struct.unpack("IIII",f.read(16))
            image_source, image_no, image_base, _ = struct.unpack("IIII",f.read(16))

            # choose material
            mat_found = False

            if image_source == 1:
                if image_no == 0xffffffff:
                    image_no = self.num_GB_tex - 1
                texName = "GB_Tex_" + str(image_no)
                non_MDL_tex += 1
                mat_found = True
            elif image_source == 2:
                if image_no == 0xffffffff:
                    image_no = self.num_GB_tex - 1
                texName = "TR_Tex_" + str(image_no)
                non_MDL_tex += 1
                mat_found = True
            elif image_source == 3:
                if image_no == 0xffffffff:
                    image_no == self.num_tex - 1
                texName = "Tex_" + str(image_no-non_MDL_tex)
                print ("found MDL tex",image_no, index, non_MDL_tex, texName)
                mat_found = True

            if mat_found:                                
                matName = "Mat_"+str(index)
                print ("material ", matName, texName)
                material = NoeMaterial(matName,texName)               
                # some models have flipped face vertex order
                #material.setFlags(noesis.NMATFLAG_TWOSIDED, 0)

                # somehow this blending for shadow has no effect
                #material.setBlendMode(noesis.NOEBLEND_ONE, noesis.NOEBLEND_ONE_MINUS_SRC_ALPHA)
                
                material.setTexture(texName)
                #print ("blend ",material.blendSrc, material.blendDst)
                #print(dir(material))
                self.matList.append(material)

                rapi.rpgSetMaterial(matName)
            else:
                rapi.rpgSetMaterial("")    

            mesh_group_info = MeshGroupInfo(index)
            self.parse_meshes(f, offs + data_start_offs, mesh_group_info)
            index += 1
            offs = next_offs

    def parse_meshes(self, f, offs, mesh_group_info):
        index = 0
        while offs > 0:
            f.seek(offs, NOESEEK_ABS)
            next_offs, data_start_offs, total_size, _ = struct.unpack("IIII",f.read(16))
            clut_index, _, _, flag = struct.unpack("IIII",f.read(16))
            mesh_info = MeshInfo(index, flag, mesh_group_info)
            self.parse_submeshes(f, offs + data_start_offs, mesh_info)
            index += 1
            offs = next_offs

    def parse_submeshes(self, f, offs, mesh_info):
        index = 0
        while offs > 0:
            f.seek(offs, NOESEEK_ABS)
            next_offs, data_start_offs, total_size, _ = struct.unpack("IIII",f.read(16))
            submesh_info = SubmeshInfo(index, mesh_info)
            self.parse_shapes(f, offs + data_start_offs, submesh_info)
            index += 1
            offs = next_offs

    def parse_shapes(self, f, offs, submesh_info):
        index = 0
        while offs > 0:
            f.seek(offs)
            next_offs, data_start_offs, total_size, _ = struct.unpack("IIII",f.read(16))
            vertex_count, transform_index, _, _ = struct.unpack("IIII",f.read(16))        
            f.seek(offs + data_start_offs)

            vtx = []
            tri = []
            vn = []
            uv = []
            vcol = []
            reverse = False
            v1 =  NoeVec4([0,0,0,0])
            v2 =  NoeVec4([0,0,0,0])       
            tri_cnt = 0
            for i in range(vertex_count):

                vtx_a = NoeVec3([v for v in struct.unpack("fff",f.read(12))])
                vtx_local = vtx_a.toVec4()
                vt  = self.global_matrix * vtx_local
                vv = vt # / 100.0  #scale it down
                vtx.extend([vv[0],vv[1],vv[2]])
                
                vn.extend(struct.unpack("fff",f.read(12)))
                uv_val = struct.unpack("ff",f.read(8))
                uv.extend([uv_val[0], uv_val[1]])
                unknown = f.read(4)

                flag = (v1 == v2 or v2 == vv or v1 == vv)
                if i > 1 and not flag:
                    tri_cnt += 1
                    if reverse:
                        tri.extend([i, i - 1, i - 2])
                    else:
                        tri.extend([i - 2, i - 1, i])
                reverse = not reverse
                v1=v2
                v2=vv
            # Build mesh at the shape level.
            offs_str = '{0:#010x}'.format(offs)
            objname = 'Mesh_'
            objname += str(submesh_info.mesh_info.mesh_group_info.index)+'_'
            objname += str(submesh_info.mesh_info.index)+'_'
            objname += str(submesh_info.index)+'_'
            objname += str(index)+'_'+offs_str+'_'+hex(submesh_info.mesh_info.flag)
            
            rapi.rpgSetName( objname )
            rapi.rpgSetPosScaleBias((MeshScale, MeshScale, MeshScale), (0, 0, 0))
            
            print (objname)

            # flip mesh along y-axis (vertial direction)
            rapi.rpgSetTransform(NoeMat43((NoeVec3((-1, 0, 0)), NoeVec3((0, -1, 0)), NoeVec3((0, 0, 1)), NoeVec3((0, 0, 0)))))     

            vertB = struct.pack("<" + 'f'*len(vtx), *vtx)        
            normBuff = struct.pack("<" + 'f'*len(vn), *vn)
            uvBuff = struct.pack("<" + 'f'*len(uv), *uv)
            faceBuff = struct.pack("<" + 'I'*len(tri), *tri)            

            rapi.rpgBindPositionBufferOfs(vertB, noesis.RPGEODATA_FLOAT, 0xc, 0x0)
                
            rapi.rpgBindNormalBufferOfs(normBuff, noesis.RPGEODATA_FLOAT, 0xC, 0x0)
            
            rapi.rpgBindUV1BufferOfs(uvBuff, noesis.RPGEODATA_FLOAT, 0x8, 0x0)

            rapi.rpgCommitTriangles(faceBuff, noesis.RPGEODATA_UINT, len(tri), noesis.RPGEO_TRIANGLE, 0x1)
                
            rapi.rpgClearBufferBinds() 

            index += 1
            offs = next_offs                                              

def meshLoadModel(data, mdlList):
    ctx = rapi.rpgCreateContext()
    mesh = meshFile(data)
    mesh.loadMesh()
    try:
        mdl = rapi.rpgConstructModel()
    except:
        mdl = NoeModel()
    mdl.setModelMaterials(NoeModelMaterials(mesh.texList, mesh.matList))
    mdlList.append(mdl);

    return 1
        
