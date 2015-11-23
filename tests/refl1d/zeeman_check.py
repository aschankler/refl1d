from os.path import join as joinpath, dirname, exists, getmtime as filetime
import tempfile
import os

import numpy as np
from numpy import radians

from bumps.util import pushdir
from refl1d.reflectivity import magnetic_amplitude as refl

H2K = 2.91451e-5
B2SLD = 2.31929e-06
GEPORE_SRC = 'gepore_zeeman.f'

def add_H(layers, H=0.0, AGUIDE=270.0):
    """ Take H (vector) as input and add H to 4piM:
    """
    new_layers = []
    for layer in layers:
        thickness, sld_n, sld_m, theta_m, phi_m = layer
        # we read phi_m, but it must be zero so we don't use it.
        sld_m_x = sld_m * np.cos(theta_m*np.pi/180.0) # phi_m = 0
        sld_m_y = sld_m * np.sin(theta_m*np.pi/180.0) # phi_m = 0
        sld_m_z = 0.0 # by Maxwell's equations, H_demag = mz so we'll just cancel it here
        sld_h = B2SLD * 1.0e6 * H        
        # this code was completely wrong except for the case AGUIDE=270
        sld_h_x = 0 # by definition, H is along the z,lab direction and x,lab = x,sam so Hx,sam must = 0
        sld_h_y = -sld_h * np.sin(AGUIDE*np.pi/180.0)
        sld_h_z =  sld_h * np.cos(AGUIDE*np.pi/180.0)
        sld_b_x = sld_h_x + sld_m_x
        sld_b_y = sld_h_y + sld_m_y
        sld_b_z = sld_h_z + sld_m_z
        sld_b = np.sqrt((sld_b_z)**2 + (sld_b_y)**2 + (sld_b_x)**2)
        theta_b = np.arctan2(sld_b_y, sld_b_x)
        theta_b = np.mod(theta_b, 2.0*np.pi)
        phi_b = np.arcsin(sld_b_z/sld_b)
        phi_b = np.mod(phi_b, 2.0*np.pi)
        new_layer = [thickness, sld_n, sld_b, theta_b*180.0/np.pi, phi_b*180.0/np.pi]
        new_layers.append(new_layer)
    return new_layers

def gepore(layers, QS, DQ, NQ, EPS, H):
    #if H != 0:
    layers = add_H(layers, H, AGUIDE=EPS)
    depth, rho, rhoM, thetaM, phiM = list(zip(*layers))

    NL = len(rho)-2
    NC = 1
    ROSUP = rho[-1] + rhoM[-1]
    ROSUM = rho[-1] - rhoM[-1]
    ROINP = rho[0]  +  rhoM[0]
    ROINM = rho[0]  -  rhoM[0]

    path = tempfile.gettempdir()
    header = joinpath(path, 'inpt.d')
    layers = joinpath(path, 'tro.d')
    rm_real = joinpath(path, 'rrem.d')
    rm_imag = joinpath(path, 'rimm.d')
    rp_real = joinpath(path, 'rrep.d')
    rp_imag = joinpath(path, 'rimp.d')

    # recompile gepore if necessary
    gepore = joinpath(path, 'gepore')
    gepore_source = joinpath(dirname(__file__), '..','..','refl1d','lib',GEPORE_SRC)
    if not exists(gepore) or filetime(gepore) < filetime(gepore_source):
        status = os.system('gfortran -O2 -o %s %s'%(gepore,gepore_source))
        if status != 0:
            raise RuntimeError("Could not compile %r"%gepore_source)
        if not exists(gepore):
            raise RuntimeError("No gepore created in %r"%gepore)

    with open(layers, 'w') as fid:
        for T,BN,PN,THE in list(zip(depth,rho,rhoM,thetaM))[1:-1]:
            fid.write('%f %e %e %f %f\n'%(T,1e-6*BN,1e-6*PN,radians(THE),0.0))

    for IP in (0.0, 1.0):
        with open(header, 'w') as fid:
            fid.write('%d %d %f %f %d %f (%f,0.0) (%f,0.0) %e %e %e %e\n'
                      %(NL,NC,QS,DQ,NQ,radians(EPS),IP,1-IP,
                        1e-6*ROINP,1e-6*ROINM,1e-6*ROSUP,1e-6*ROSUM))
        with pushdir(path):
            status = os.system('./gepore') # >/dev/null')
            if status != 0:
                raise RuntimeError("Could not run gepore")
        rp = np.loadtxt(rp_real).T[1] + 1j*np.loadtxt(rp_imag).T[1]
        rm = np.loadtxt(rm_real).T[1] + 1j*np.loadtxt(rm_imag).T[1]
        if IP == 1.0:
            Rpp, Rpm = rp, rm
        else:
            Rmp, Rmm = rp, rm
    return Rmm, Rpm, Rmp, Rpp

def magnetic_cc(layers, kz, Aguide, H):
    depth, rho, rhoM, thetaM, phiM = list(zip(*layers))
    R = refl(kz, depth, rho, 0, rhoM, thetaM, 0, Aguide, H, rotate_M=True)
    return R

def Rplot(Qz, R, format):
    import pylab
    pylab.hold(True)
    for name,xs in zip(('++','+-','-+','--'),R):
    #for name,xs in zip(('--','-+','+-','++'),R):
        Rxs = abs(xs)**2
        if (Rxs>1e-8).any():
            pylab.plot(Qz, Rxs, format, label=name)
    pylab.xlabel('$2k_{z0}$', size='large')
    pylab.ylabel('R')
    pylab.legend()

def rplot(Qz, R, format):
    import pylab
    pylab.hold(True)
    pylab.figure()
    for name,xs in zip(('++','+-','-+','--'),R):
        rr = xs.real
        if (rr>1e-8).any():
            pylab.plot(Qz, rr, format, label=name + 'r')
    pylab.legend()
    pylab.figure()
    for name,xs in zip(('++','+-','-+','--'),R):
        ri = xs.imag
        if (ri>1e-8).any():
            pylab.plot(Qz, ri, format, label=name + 'i')
    pylab.legend()

    pylab.figure()
    for name,xs in zip(('++','+-','-+','--'),R):
        phi = np.arctan2(xs.imag, xs.real)
        if (ri>1e-8).any():
            pylab.plot(Qz, phi, format, label=name + 'i')
    pylab.legend()

def compare(name, layers, Aguide=270, H=0):

    QS = 0.001
    DQ = 0.0001
    NQ = 500
    Rgepore = gepore(layers, QS, DQ, NQ, Aguide, H)
    
    Qz = np.arange(NQ)*DQ+QS
    kz = Qz[::2]/2
    Rrefl1d = magnetic_cc(layers, kz, Aguide, H)

    Rplot(Qz, Rgepore, '+'); 
    Rplot(2*kz, Rrefl1d, '-'); import pylab; pylab.show(); return kz, Rrefl1d

    assert np.linalg.norm((R[0]-Rpp)/Rpp) < 1e-13, "fail ++ %s"%name
    assert np.linalg.norm((R[1]-Rpm)/Rpm) < 1e-13, "fail +- %s"%name
    assert np.linalg.norm((R[2]-Rmp)/Rmp) < 1e-13, "fail -+ %s"%name
    assert np.linalg.norm((R[3]-Rmm)/Rmm) < 1e-13, "fail -- %s"%name

def simple():
    Aguide = 270
    layers = [
        # depth rho rhoM thetaM phiM
        [ 0, 0.0, 0.0, 270, 0],
        [200, 4.0, 1.0, 359.9, 0.0],
        [200, 2.0, 1.0, 270, 0.0],
        [ 0, 4.0, 0.0, 270, 0.0],
    ]
    return "Si-Fe-Au-Air", layers, Aguide

def twist():
    Aguide = 270
    layers = [
        # depth rho rhoM thetaM phiM
        [ 0, 2.1, 0.0, 270, 0.0],
        [20, 8.0, 5.0, 270, 0.0],
        [20, 8.0, 5.0, 220, 0.0],
        [20, 8.0, 5.0, 180, 0.0],
        [10, 4.5, 0.0, 270, 0.0],
        [ 0, 0.0, 0.0, 270, 0.0],
        ]
    return "twist", layers, Aguide

def magsub():
    Aguide = 270
    layers = [
        # depth rho rhoM thetaM phiM
        [50, 8.0, 5.0, 270, 0.0],
        [ 0, 2.1, 0.0, 270, 0.0],
        [10, 4.5, 0.0, 270, 0.0],
        [ 0, 0.0, 0.0, 270, 0.0],
        ]
    return "magnetic substrate", layers, Aguide

def magsurf():
    Aguide = 270
    layers = [
        # depth rho rhoM thetaM phiM
        [ 0, 0.0, 0.0, 270, 0.0],
        [200, 4.0, 1.0, 0.01, 0.0],
        [200, 2.0, 1.0, 270, 0.0],
        [200, 4.0, 0.0, 270, 0.0],
        ]
    return "magnetic surface", layers, Aguide

def NSF_example():
    Aguide = 270.0
    layers = [
        # depth rho rhoM thetaM phiM
        [ 0, 0.0, 1e-6, 90, 0.0],
        [200, 4.0, 1.0, 90, 0.0],
        [200, 2.0, 1.0, 90, 0.0],
        [200, 4.0, 1e-6, 90, 0.0],
        ]
    return "non spin flip", layers, Aguide
    
def Yaohua_example():
    Aguide = 270.0
    rhoB = B2SLD * 0.4 * 1e6
    layers = [
        # depth rho rhoM thetaM phiM
        [ 0, 0.0, rhoB, 90, 0.0],
        [ 200, 4.0, rhoB + 1.0, np.degrees(np.arctan2(rhoB, 1.0)), 0.0],
        [ 200, 2.0, rhoB + 1.0, 90, 0.0],
        [ 0, 4.0, rhoB, 90 , 0.0],
        ]
    return "Yaohua example", layers, Aguide
    
def zf_Yaohua_example():
    Aguide = 270.0
    layers = [
        # depth rho rhoM thetaM phiM
        [ 0, 0.0, 0.0, 90, 0.0],
        [ 200, 4.0, 1.0, 0.0001, 0.0],
        [ 200, 2.0, 1.0, 90, 0.0],
        [ 0, 4.0, 0.0, 90, 0.0],
        ]
    return "Yaohua example", layers, Aguide 

def Chuck_test():
    Aguide = 270.0
    layers = [
        # depth rho rhoM thetaM phiM
        [ 0, 2.0, 2.0, 90.0, 0.0],
        [ 200, 6.0, 4.0, 0.0001, 0.0],
        [ 300, 6.0, 4.0, 0.0001, 0.0],
        [ 0, 5.0, 0.0001, 90, 0.0],
    ]
    return "Chuck example", layers, Aguide

def Kirby_test():
    Aguide = 5.0
    layers = [
        # depth rho rhoM thetaM phiM
        [ 0, 0.0, 0.0, 90, 0.0],
        [ 50, 4.0, 0, 0.001, 0.0],
        [ 825, 9.06, 1.46, 0.0001, 0],
        [ 0, 2.07, 0.0001, 90, 0.0],
    ]
    return "Kirby example", layers, Aguide
    
def demo():
    """run demo"""
    import pylab
    #compare(*simple())
    #compare(*twist())
    #compare(*magsub())
    #compare(*magsurf())
    pylab.figure()
    compare(*zf_Yaohua_example(), H=0.0005) # 5 Gauss
    pylab.figure()
    compare(*zf_Yaohua_example(), H=0.4) # 4000 gauss
    pylab.figure()
    compare(*NSF_example(), H=0.00005) # Earth's field, 0.5G
    pylab.figure()
    compare(*NSF_example(), H=1.0) # 1 tesla
    pylab.figure()
    compare(*Chuck_test(), H=0) # zeroish field, but magnetic front
    pylab.figure()
    compare(*Kirby_test(), H=0.000244)
    pylab.show()

def write_Chuck_result():
    kz, R = compare(*Chuck_test(), H=0) # zeroish field, but magnetic front
    np.savetxt('Rmm.txt', np.vstack((2*kz, np.abs(R[3])**2)).T,  delimiter="\t")
    np.savetxt('Rmp.txt', np.vstack((2*kz, np.abs(R[2])**2)).T,  delimiter="\t")
    np.savetxt('Rpm.txt', np.vstack((2*kz, np.abs(R[1])**2)).T,  delimiter="\t")
    np.savetxt('Rpp.txt', np.vstack((2*kz, np.abs(R[0])**2)).T,  delimiter="\t")


if __name__ == "__main__":
    demo()
