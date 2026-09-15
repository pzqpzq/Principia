import numpy as np
import scipy as sci
import matplotlib.pyplot as plt
import networkx as nx
import os
import h5py

import myPy_functions

# os.chdir('D:\Documents\PostDoc_KTH\WACQT_Project\PyPump\Engineering_PumpingScheme\Codes')
# sys.path.append(os.getcwd())
# import PyPump as pp


def mode_to_index(mode_number,tot_modes):
    #INPUT:
    # mode_number: the label of a given mode
    # tot_modes : total number of modes
    #OUTPUT:
    # index: the vector index of the given mode (0..tot_modes-1)
    if tot_modes % 2 == 0:  #number of modes is even (labels go from -tot_mod/2 ..-1,1..+tot_mod/2 --> no mode 0)
        if mode_number==0:
            print('For even number of modes, mode 0 is not defined!')
            index=-1
        else:
            index = int(mode_number + (tot_modes)/2)
            if index>=(tot_modes)/2:
                index=index-1
    else:                   #number of modes is odd (labels go from -(tot_mod-1)/2 ..-1,0,1..+(tot_mod-1)/2)
        index = int(mode_number + (tot_modes-1)/2)
    return index

def mode_to_index_FullM(mode_number,antm_flg,tot_modes):
    # INPUT:
    # mode_number: the label of a given mode
    # antm_flg: "mode anti-mode flag" 0 --> mode (1 --> antimode):  Return index position of mode (antimode) in M
    # tot_modes : total number of modes
    # OUTPUT:
    # index: the vector index of the given mode (0..tot_modes-1)
    #
    # M is a 2*tot_modes x 2*tot_modes matrix with modes on even indices and antimodes on odd indeces
    #
    index=mode_to_index(mode_number,tot_modes)
    if ( index>=0 ):    #no error
        index=2*index
        #Check mode/antimode
        if antm_flg==1:
            index = index+1
    return index

def modeindex_connected_byPump_with_allModes(m_index, allmodes_freq, gp, omega_p):
    """
    Calculate the indices and coupling coefficients of the modes connected to a given mode by a pump.

    Parameters:
        m_index (int): Index of the mode.
        allmodes_freq (ndarray): Array of all mode frequencies.
        gp (complex): Coupling coefficient.
        omega_p (float): Pump frequency.

    Returns:
        indices (ndarray): Array of indices of the connected modes.
        gij (ndarray): Array of coupling coefficients for the connected modes.
    """
    spacing = allmodes_freq[2] - allmodes_freq[0]

    # Get the frequency of the mode
    omega_i = allmodes_freq[m_index]
    sign_gij = -1 if m_index % 2 == 0 else +1

    # Check for all modes(and antimodes) if they can be connected by the pump to mode i
    omega_plus = allmodes_freq + omega_p
    omega_minus = allmodes_freq - omega_p

    mask_plus = ((omega_i - spacing / 2) <= omega_plus) & (
        omega_plus < (omega_i + spacing / 2)
    )
    mask_minu = ((omega_i - spacing / 2) <= omega_minus) & (
        omega_minus < (omega_i + spacing / 2)
    )

    mask_minu[m_index] = False  # Exclude the mode itself
    mask_plus[m_index] = False  # Exclude the mode itself

    # Calculate gij
    gij = np.zeros(len(allmodes_freq), dtype=np.complex128)
    gij[mask_plus] = sign_gij * gp / 2
    gij[mask_minu] = sign_gij * np.conjugate(gp) / 2

    # Extract indices
    indices = np.where(mask_plus | mask_minu)[0]

    return indices, gij

def modeindex_connected_byPump(m_index,nmodes, modes_freq, gp, omega_p):
    # INPUT:
    # m_index:  index of the mode (even for modes, odd for antimodes)
    # nmodes:   number of modes
    # modes_frequencies: list of positive frequencies (of nmodes)
    # gp:       complex pump strength
    # omega_p:  pump frequency
    #
    # OUTPUT:
    # List_index: list of mode indices connected by the Pump
    # List_gij: list of coupling constants gij between mode i and each mde j connected bby the pump

    #Generate vector with both positive and negative freq as in M (w1,-w1,w2,-w2,...,wi,-wi,...)
    allmodes_freq = np.zeros(2*len(modes_freq))
    allmodes_freq[0::2] = modes_freq
    allmodes_freq[1::2] = -modes_freq

    # Call to new, more specific function
    return modeindex_connected_byPump_with_allModes(m_index, allmodes_freq, gp, omega_p)


def generate_freq_vectors(nmodes,omega0,Delta):
    # INPUT:
    # nmodes: number of modes
    # omega0: modes center frequency (center of the bandwidth)
    # Delta: mode spacing
    #
    # OUTPUT:
    # modes_freq: vector containing all positive modes frequencies (w1,w2,,...,omega0,...,wn-1,wn)
    # modes_range: vector containing modes labels. Odd nmodes: (-n,..,-2,-1,0,1,2,..,n); even nmodes (-n,..,-2,-1,1,2,..,n)
    # allmodes_freq: vector containing both positive and negative freq as in M (w1,-w1,w2,-w2,...,wi,-wi,...)

    if nmodes % 2 == 0:  # even number of modes (no mode 0)
        top = int(nmodes / 2)
        modes_neg = np.arange(-top, -1 + 1)  # +1 because python range is stupid (it excludes the last)
        modes_pos = np.arange(1, top + 1)  # +1 because python range is stupid (it excludes the last)
        modes_range = np.concatenate((modes_neg, modes_pos))
        neg_freq = Delta * modes_neg + Delta / 2
        pos_freq = Delta * modes_pos - Delta / 2
        modes_freq = np.concatenate((neg_freq, pos_freq)) + omega0
    else:  # odd number of modes
        top = int((nmodes - 1) / 2)
        modes_range = np.arange(-top, top + 1)  # +1 because python range is stupid (it excludes the last)
        modes_freq = Delta * modes_range + omega0

    # Generate vector with both positive and negative freq as in M (w1,-w1,w2,-w2,...,wi,-wi,...)
    allmodes_freq = np.zeros(2 * nmodes)
    i = 0
    for fi in modes_freq:
        allmodes_freq[i] = fi
        allmodes_freq[i + 1] = -fi
        i = i + 2
    return modes_freq,modes_range,allmodes_freq

def compute_M(omega0,nmodes,allmodes_freq,modes_freq,gamma,Npumps,gp,omega_p):
    # INPUT:
    # omega0: modes center frequency (central resonant frequency of the JPA)
    # nmodes: number of modes
    # allmodes_freq: vector containing both positive and negative freq as in M (w1,-w1,w2,-w2,...,wi,-wi,...)
    # modes_freq: vector containing all positive modes frequencies (w1,w2,,...,omega0,...,wn-1,wn)
    # gamma: = gamma_ext + gamma_int : dissipative term
    # Npumps: the number of pumps
    # gp: vector containing the complex pump strength for each pump
    # omega_p: vector containing the pump frequency of each pump
    #
    # OUTPUT:
    # M: Matrix M from Equation of Motions in the form: -iM a_vec=K a_in
    # M_inv: inverse matrix of M such that M_inv*M = M*M_inv = 1
    # Diagonal terms of M
    M = np.diag(-allmodes_freq + 1j * gamma / 2)
    # Omega Matrix/List
    M_omega = omega0 * np.ones((2 * nmodes), dtype=np.complex128)
    M_omega[0::2] = -M_omega[0::2]                                  #Modes: -omega_i -omega_0 +1igamma/2; Antimodes: +omega_i +omega_0 +1igamma/2
    M = M + np.diag(M_omega)

    # Iterate pump contributions
    for _gp, _omega_p in zip(gp, omega_p):
        for i in range(2 * nmodes):
            _, gij_mode = modeindex_connected_byPump_with_allModes(i, allmodes_freq, _gp, _omega_p)
            # Add the coupling coefficients to the matrix M
            M[i] += gij_mode

    return M, np.linalg.inv(M)


def compute_S_norm(omega0,Delta,nmodes,gamma_tune,gp,omega_p):
    #Compute the small S already normalized with the 0 pump case
    Npumps=len(gp)
    modes_freq, modes_labels, allmodes_freq = generate_freq_vectors(nmodes, omega0, Delta)
    # Dissipation Rates
    gamma_int = 0.
    gamma_ext = 2 * np.pi * 100 * (10 ** 6) / (10 ** 9)  # [GHz]
    gamma0_ext = gamma_ext * gamma_tune
    gamma = gamma_int + gamma0_ext

    #Call fcn to compute M and Minv
    M, M_inv = compute_M(omega0, nmodes, allmodes_freq, modes_freq, gamma, Npumps, gp, omega_p)

    # Compute Scattering Matrix S
    Id = np.identity(2 * nmodes)
    K = np.identity(2 * nmodes) * np.sqrt(gamma0_ext)
    Saa = 1j * K.dot(M_inv).dot(K) - Id

    # Compute the reference (zero-pump case)
    Npump_ref = 1
    g0ref = np.zeros((Npump_ref), dtype=complex)
    omega_pref= np.zeros((Npump_ref))
    omega_pref[0]= Delta * 2000
    M0ref, M0ref_inv = compute_M(omega0, nmodes, allmodes_freq, modes_freq, gamma, 1, g0ref, omega_pref)
    S0aa_ref = 1j * K.dot(M0ref_inv).dot(K) - Id
    S0a_ref = extract_small_S(S0aa_ref)
    S0num_ref = np.mean(np.abs(np.diag(S0a_ref)))  # Compute the mean of the diagonal elements'abs valu

    # Extract small S and normalize it with zero-pump case
    S = extract_small_S(Saa)

    return S, S0num_ref

def index_of_mlabel(label,vec_labels,flag_antmode):
    # Return position of label in vector vec_labels
    # flag_antimode: (0) to return mode index; (1) for antimode index
    #
    # Notice full-M mode configuration is used and mode-antimode ordering: (-M,-M*,...-1,-1*,0,0*,1,1*,...,M,M*)

    ind = np.where(vec_labels == label)
    index = 2*int(ind[0])
    if (flag_antmode==1):
        index=index+1
    return index

def is_a_mode(index):
    # Return 1 if index is a mode, 0 if it's an anti-mode
    # index: integer of modes in Full-M representation (-M,-M*,...-1,-1*,0,0*,1,1*,...,M,M*)

    if ( (index % 2) == 0):
        output=1
    else:
        output=0
    return output


def extract_small_S(S):
    # Compute the n-by-n S-matrix (pos frequency only) from the 2n-by-2n numerical S-matrix to compare with experimental data
    # INPUT:
    # S: S 2n-by-2n scattering matrix with mode antimode ordering (-M,-M*,...-1,-1*,0,0*,1,1*,...,M,M*)
    # OUTPUT:
    # Small: n-by-n scattering matrix comparable with experiment (positive freq. only, but contribution from both pos. and neg. freq. processes)

    n=int(len(S)/2)      #Assuming S square matrix 2n-by-2n
    Small = np.zeros((n, n), dtype=complex)
    i = 0
    while (i < n):
        j = 0
        while (j < n):
            Small[i, j] = S[2 * i, 2 * j] + S[2 * i + 1, 2 * j]  # Both positive freq. contribution of mode and antimodes contributes to the output of mode i
            j = j + 1
        i = i + 1

    return Small

def dB(Sjk):
    return 20 * np.log10(np.abs(Sjk))

def dBpwr(Sjk):
    return 10 * np.log10(np.abs(Sjk))

def compute_Mdist(A,B):
    # Computes the 2D distance between A and B defined according to the norm-2 definition:
    #   d=\sqrt{ \sum_ij |Aij-Bij|^2 }
    return np.sum(np.abs(A - B)**2)**0.5

def compute_Mdist_nodiag(A,B):
    # Computes the 2D distance between matrices A and B WITHOUT the diagonal.
    # Defined according to the norm-2 definition:
    #   d=\sqrt{ \sum_{i\neq j} |Aij-Bij|^2 }
    if (A.shape==B.shape):
        Ni, Nj = A.shape
        dist=0
        i=0
        while (i<Ni):
            j=0
            while (j<Nj):
                if (i != j):
                    dist=dist + np.abs(A[i,j] - B[i,j])
                j+=1
            i+=1
        dist=np.sqrt(dist)
    else:
        dist=-1
        print('Error! Matrix sizes do not match')
    return dist

def compute_Mdist_3antDiagsOnly(A,B,k):
    # Computes the 2D distance between matrices A and B for anly 3 anti-diagonal k,spaced.
    # Defined according to the norm-2 definition:
    #   d=\sqrt{ \sum_{i\neq j} |Aij-Bij|^2 }
    if (A.shape==B.shape):
        Ni, Nj = A.shape
        dist=0
        i=0
        #Main anti-diag
        while (i<Ni):
            dist=dist + np.abs(A[i,Ni-1-i] - B[i,Ni-1-i])
            i+=1
        dist=np.sqrt(dist)
        # -k anti-diag
        while (i < Ni-k):
            dist = dist + np.abs(A[i, Ni-1-k - i] - B[i, Ni-1-k - i])
            i += 1
        dist = np.sqrt(dist)
        # +k anti-diag
        i=k-1
        while (i < Ni ):
            dist = dist + np.abs(A[i, Ni-1 - i] - B[i, Ni-1 - i])
            i += 1
        dist = np.sqrt(dist)
    else:
        dist=-1
        print('Error! Matrix sizes do not match')
    return dist

def print_Smatrix(S, fig0=None, ax0=None):
    # 3pmp-case bckgnd and 0-ref for dB threshold
    if ( (fig0==None) and (ax0==None)):
        fig0, ax0 = plt.subplots(1, 1, figsize=(8, 5))
    S0exp_ref = 0.00035796379677849094
    background = 1.5060476433580897e-06
    bckgnd_dB=-60 #[dB]
    #Extract small S
    Snum = extract_small_S(S)
    Snum_abs = np.abs(Snum)
    Snum_ang = np.angle(Snum)
    pl01 = ax0.imshow(dB(Snum_abs + 10**(bckgnd_dB/20)), cmap='RdBu_r', vmin=bckgnd_dB, vmax=10)
    # pl1=ax.imshow(Sabs,norm=colors.LogNorm(vmin = 0.0001,vmax = 3),cmap='RdBu_r',extent=[-top,top,top,-top]) #log scale
    plt.colorbar(pl01, ax=ax0)
    ax0.set_title('$|S|$ ', fontsize=15)
    return

def plot_Smatr(S):
    fig0, ax0 = plt.subplots(1, 2, figsize=(10,5))
    pl01 = ax0[0].imshow(np.abs(S), cmap='RdBu_r')
    plt.colorbar(pl01, ax=ax0[0])
    ax0[0].set_title('$|S|$ ', fontsize=15)
    pl02 = ax0[1].imshow(np.angle(S), cmap='RdBu_r')
    plt.colorbar(pl02, ax=ax0[1])
    ax0[1].set_title('$\\angle S$ ', fontsize=15)
    return

def print_Sxp(S):
    fig0, ax0 = plt.subplots(1, 2, figsize=(15,10))
    pl01 = ax0[0].imshow(np.real(S), cmap='RdBu_r')
    plt.colorbar(pl01, ax=ax0[0])
    ax0[0].set_title('Re{$S$} ', fontsize=15)
    pl02 = ax0[1].imshow(np.imag(S), cmap='RdBu_r')
    plt.colorbar(pl02, ax=ax0[1])
    ax0[1].set_title('Im{$S$} ', fontsize=15)
    return

def print_Matrix(M):
    fig0, ax0 = plt.subplots(1, 2, figsize=(15,10))
    pl01 = ax0[0].imshow(np.real(M), cmap='RdBu_r')
    plt.colorbar(pl01, ax=ax0[0])
    ax0[0].set_title('Re ', fontsize=15)
    pl02 = ax0[1].imshow(np.imag(M), cmap='RdBu_r')
    plt.colorbar(pl02, ax=ax0[1])
    ax0[1].set_title('Im ', fontsize=15)
    return

def plot_Matr(M, str='M', scale=None, extent=None, fig=None, ax=None):
    if ( scale == None ):
        scale=np.max(np.abs(M))   
    if ( extent == None ):
        n=M.shape[0]
        top=n//4
    if ( ( fig == None ) or ( ax == None ) ):
        fig, ax = plt.subplots(1, 1, figsize=(10,10))
    pl01 = ax.imshow(M, cmap='RdBu_r',
                      extent=[-top, top, top, -top],
                      vmin=-scale,
                      vmax=scale,
                      aspect='equal'
                     )
    fig.colorbar(pl01, ax=ax)
    ax.set_title(str, fontsize=15)
    return

def plot_Matrix(M, str='M', col_map=None, scale=None, extent=None, fig=None, ax=None):
    if ( col_map==None ):
        col_map = 'RdBu_r'
    if ( scale == None ):
        Mmax = np.max(np.abs(M)) 
        Mmin = np.min(np.abs(M))  
    else:
        Mmax = scale
        Mmin = -scale
    if ( extent == None ):
        n=M.shape[0]
        top=n//4
    if ( ( fig == None ) or ( ax == None ) ):
        fig, ax = plt.subplots(1, 1, figsize=(10,10))
    pl01 = ax.imshow(M, cmap=col_map,
                      extent=[-top, top, top, -top],
                      vmin=Mmin,
                      vmax=Mmax,
                      aspect='equal'
                     )
    fig.colorbar(pl01, ax=ax)
    ax.set_title(str, fontsize=15)
    return

def print_squeezingTest(lab_i,lab_j,xp_0,xp_out):
    Nxp, Ndata = xp_0.shape
    nmodes=Nxp/2
    mode_i = 2 * mode_to_index(lab_i, nmodes)
    mode_j = 2 * mode_to_index(lab_j, nmodes)
    x0_i = xp_0[mode_i, :]
    p0_i = xp_0[mode_i + 1, :]
    x0_j = xp_0[mode_j, :]
    p0_j = xp_0[mode_j + 1, :]
    xout_i = xp_out[mode_i, :]
    pout_i = xp_out[mode_i + 1, :]
    xout_j = xp_out[mode_j, :]
    pout_j = xp_out[mode_j + 1, :]
    fig0, ax0 = plt.subplots(2, 3, figsize=(15, 10))
    ## x-p
    # i-i
    pl001 = ax0[0][0].plot(x0_i, p0_i, '.')
    pl002 = ax0[0][0].plot(xout_i, pout_i, '.')
    ax0[0][0].set_xlabel('$\langle x_{}\\rangle$'.format(lab_i))
    ax0[0][0].set_ylabel('$\langle p_{}\\rangle$'.format(lab_i))
    ax0[0, 0].axis('equal')
    ax0[0, 0].legend(['vacuum', 'output'], frameon=False)
    # i-j
    pl011 = ax0[0][1].plot(x0_i, p0_j, '.')
    pl012 = ax0[0][1].plot(xout_i, pout_j, '.')
    ax0[0][1].set_xlabel('$\langle x_{}\\rangle$'.format(lab_i))
    ax0[0][1].set_ylabel('$\langle p_{}\\rangle$'.format(lab_j))
    ax0[0, 1].axis('equal')
    ax0[0, 1].legend(['vacuum', 'output'], frameon=False)
    # j-i
    pl101 = ax0[1][0].plot(x0_j, p0_i, '.')
    pl102 = ax0[1][0].plot(xout_j, pout_i, '.')
    ax0[1][0].set_xlabel('$\langle x_{}\\rangle$'.format(lab_j))
    ax0[1][0].set_ylabel('$\langle p_{}\\rangle$'.format(lab_i))
    ax0[1, 0].axis('equal')
    ax0[1, 0].legend(['vacuum', 'output'], frameon=False)
    # j-j
    pl111 = ax0[1][1].plot(x0_j, p0_j, '.')
    pl112 = ax0[1][1].plot(xout_j, pout_j, '.')
    ax0[1][1].set_xlabel('$\langle x_{}\\rangle$'.format(lab_j))
    ax0[1][1].set_ylabel('$\langle p_{}\\rangle$'.format(lab_j))
    ax0[1, 1].axis('equal')
    ax0[1, 1].legend(['vacuum', 'output'], frameon=False)

    # xi-xj
    pl2011 = ax0[0][2].plot(x0_i, x0_j, '.')
    pl2012 = ax0[0][2].plot(xout_i, xout_j, '.')
    ax0[0][2].set_xlabel('$\langle x_{}\\rangle$'.format(lab_i))
    ax0[0][2].set_ylabel('$\langle x_{}\\rangle$'.format(lab_j))
    ax0[0][2].axis('equal')
    ax0[0, 2].legend(['vacuum', 'output'], frameon=False)
    # pi-pj
    pl2101 = ax0[1][2].plot(p0_i, p0_j, '.')
    pl2102 = ax0[1][2].plot(pout_i, pout_j, '.')
    ax0[1][2].set_xlabel('$\langle p_{}\\rangle$'.format(lab_i))
    ax0[1][2].set_ylabel('$\langle p_{}\\rangle$'.format(lab_j))
    ax0[1][2].axis('equal')
    ax0[1, 2].legend(['vacuum', 'output'],frameon=False)
    return


def print_squeezingTest_ij(lab_i,lab_j,xp_0,xp_out,fig0=None):
    Nxp, Ndata = xp_0.shape
    nmodes=Nxp/2
    mode_i = 2 * mode_to_index(lab_i, nmodes)
    mode_j = 2 * mode_to_index(lab_j, nmodes)
    x0_i = xp_0[mode_i, :]
    p0_i = xp_0[mode_i + 1, :]
    x0_j = xp_0[mode_j, :]
    p0_j = xp_0[mode_j + 1, :]
    xout_i = xp_out[mode_i, :]
    pout_i = xp_out[mode_i + 1, :]
    xout_j = xp_out[mode_j, :]
    pout_j = xp_out[mode_j + 1, :]
    if (fig0==None):
        fig0, ax0 = plt.subplots(2, 2, figsize=(10, 10))
    mksize=1
    # xi-xj
    pl2011 = ax0[0][0].plot(x0_i, x0_j, '.', markersize=mksize)
    pl2012 = ax0[0][0].plot(xout_i, xout_j, '.', markersize=mksize)
    ax0[0][0].set_xlabel('$\langle x_{}\\rangle$'.format(lab_i))
    ax0[0][0].set_ylabel('$\langle x_{}\\rangle$'.format(lab_j))
    ax0[0][0].axis('equal')
    ax0[0, 0].legend(['vacuum', 'output'], frameon=False)
    # xi-pj
    pl011 = ax0[0][1].plot(x0_i, p0_j, '.', markersize=mksize)
    pl012 = ax0[0][1].plot(xout_i, pout_j, '.', markersize=mksize)
    ax0[0][1].set_xlabel('$\langle x_{}\\rangle$'.format(lab_i))
    ax0[0][1].set_ylabel('$\langle p_{}\\rangle$'.format(lab_j))
    ax0[0, 1].axis('equal')
    ax0[0, 1].legend(['vacuum', 'output'], frameon=False)
    # xj-pi
    pl101 = ax0[1][0].plot(x0_j, p0_i, '.', markersize=mksize)
    pl102 = ax0[1][0].plot(xout_j, pout_i, '.', markersize=mksize)
    ax0[1][0].set_xlabel('$\langle x_{}\\rangle$'.format(lab_j))
    ax0[1][0].set_ylabel('$\langle p_{}\\rangle$'.format(lab_i))
    ax0[1, 0].axis('equal')
    ax0[1, 0].legend(['vacuum', 'output'], frameon=False)
    # pi-pj
    pl2101 = ax0[1][1].plot(p0_i, p0_j, '.', markersize=mksize)
    pl2102 = ax0[1][1].plot(pout_i, pout_j, '.', markersize=mksize)
    ax0[1][1].set_xlabel('$\langle p_{}\\rangle$'.format(lab_i))
    ax0[1][1].set_ylabel('$\langle p_{}\\rangle$'.format(lab_j))
    ax0[1][1].axis('equal')
    ax0[1, 1].legend(['vacuum', 'output'],frameon=False)
    return fig0, ax0


def extract_G(S,modes_labels,trig_value):
    #Given an S matrix computes the correlation/scattirng graph
    #INPUT:
    # S:            scattering matrix (big S, both modes and antimodes)
    # modes_labels: vector containing labels of each modes
    # trig_value:   threshold used to choose if two modes are connected or not
    #OUTPUT:
    # Gsq:          the networkX total graph
    # G_connected:  list of connected subgraphs in Gsq

    #3pmp-case bckgnd and 0-ref for dB threshold
    S0exp_ref = 0.00035796379677849094
    background = 1.5060476433580897e-06
    #bckgnd_dB = dB(background / S0exp_ref)
    bckgnd_dB = -60  # [dB]             #General bckground level at -60dB

    # Extract small S
    Snum = extract_small_S(S)
    Snum_abs = np.abs(Snum)
    Snum_ang = np.angle(Snum)

    #Compute the Graph
    nmodes = len(modes_labels)
    Gsq = nx.Graph()
    for i in range(0, nmodes):
        lab_i = modes_labels[i]
        Scol_i = dB(Snum_abs[:, i] + 10**(bckgnd_dB/20))
        for j in range(nmodes):
            if (Scol_i[j] >= trig_value):
                if (j != i):            #No self-neighbor
                    lab_j = modes_labels[j]
                    Gsq.add_edge(lab_i, lab_j)
    G_connected = [Gsq.subgraph(c).copy() for c in nx.connected_components(Gsq)]
    n_subg = len(G_connected)
    return Gsq, G_connected

def extract_G_Fast(k_array,mode_labels):
    Nmodes=len(mode_labels)
    Nneigh_max=len(k_array)
    list_Gi=np.zeros((Nmodes,Nneigh_max))
    mode_antidiag = np.flip(mode_labels)
    for kval in k_array:
        k_antidiag=2
    G=1
    return G #G, G_connected


def roll_zeropad(a, shift, axis=None):
    """
    Roll array elements along a given axis.

    Elements off the end of the array are treated as zeros.

    Parameters
    ----------
    a : array_like
        Input array.
    shift : int
        The number of places by which elements are shifted.
    axis : int, optional
        The axis along which elements are shifted.  By default, the array
        is flattened before shifting, after which the original
        shape is restored.

    Returns
    -------
    res : ndarray
        Output array, with the same shape as `a`.

    See Also
    --------
    roll     : Elements that roll off one end come back on the other.
    rollaxis : Roll the specified axis backwards, until it lies in a
               given position.

    Examples
    --------
    >>> x = np.arange(10)
    >>> roll_zeropad(x, 2)
    array([0, 0, 0, 1, 2, 3, 4, 5, 6, 7])
    >>> roll_zeropad(x, -2)
    array([2, 3, 4, 5, 6, 7, 8, 9, 0, 0])

    >>> x2 = np.reshape(x, (2,5))
    >>> x2
    array([[0, 1, 2, 3, 4],
           [5, 6, 7, 8, 9]])
    >>> roll_zeropad(x2, 1)
    array([[0, 0, 1, 2, 3],
           [4, 5, 6, 7, 8]])
    >>> roll_zeropad(x2, -2)
    array([[2, 3, 4, 5, 6],
           [7, 8, 9, 0, 0]])
    >>> roll_zeropad(x2, 1, axis=0)
    array([[0, 0, 0, 0, 0],
           [0, 1, 2, 3, 4]])
    >>> roll_zeropad(x2, -1, axis=0)
    array([[5, 6, 7, 8, 9],
           [0, 0, 0, 0, 0]])
    >>> roll_zeropad(x2, 1, axis=1)
    array([[0, 0, 1, 2, 3],
           [0, 5, 6, 7, 8]])
    >>> roll_zeropad(x2, -2, axis=1)
    array([[2, 3, 4, 0, 0],
           [7, 8, 9, 0, 0]])

    >>> roll_zeropad(x2, 50)
    array([[0, 0, 0, 0, 0],
           [0, 0, 0, 0, 0]])
    >>> roll_zeropad(x2, -50)
    array([[0, 0, 0, 0, 0],
           [0, 0, 0, 0, 0]])
    >>> roll_zeropad(x2, 0)
    array([[0, 1, 2, 3, 4],
           [5, 6, 7, 8, 9]])

    """
    a = np.asanyarray(a)
    if shift == 0: return a
    if axis is None:
        n = a.size
        reshape = True
    else:
        n = a.shape[axis]
        reshape = False
    if np.abs(shift) > n:
        res = np.zeros_like(a)
    elif shift < 0:
        shift += n
        zeros = np.zeros_like(a.take(np.arange(n-shift), axis))
        res = np.concatenate((a.take(np.arange(n-shift,n), axis), zeros), axis)
    else:
        zeros = np.zeros_like(a.take(np.arange(n-shift,n), axis))
        res = np.concatenate((zeros, a.take(np.arange(n-shift), axis)), axis)
    if reshape:
        return res.reshape(a.shape)
    else:
        return res


def extract_GfromSmall_S(S,modes_labels,trig_value):
    #Given an S matrix computes the correlation/scattirng graph
    #INPUT:
    # S:            scattering matrix (big S, both modes and antimodes)
    # modes_labels: vector containing labels of each modes
    # trig_value:   threshold used to choose if two modes are connected or not
    #OUTPUT:
    # Gsq:          the networkX total graph
    # G_connected:  list of connected subgraphs in Gsq

    #3pmp-case bckgnd and 0-ref for dB threshold
    S0exp_ref = 0.00035796379677849094
    background = 1.5060476433580897e-06
    #bckgnd_dB = dB(background / S0exp_ref)
    bckgnd_dB = -60  # [dB]             #General bckground level at -60dB

    # Extract small S
    Snum = S
    Snum_abs = np.abs(Snum)
    Snum_ang = np.angle(Snum)

    #Compute the Graph
    nmodes = len(modes_labels)
    Gsq = nx.Graph()
    for i in range(0, nmodes):
        lab_i = modes_labels[i]
        Scol_i = dB(Snum_abs[:, i] + 10**(bckgnd_dB/20))
        for j in range(nmodes):
            if (Scol_i[j] >= trig_value):
                if (j != i):            #No self-neighbor
                    lab_j = modes_labels[j]
                    Gsq.add_edge(lab_i, lab_j)
    G_connected = [Gsq.subgraph(c).copy() for c in nx.connected_components(Gsq)]
    n_subg = len(G_connected)
    return Gsq, G_connected

def extract_singlenode_Gi(S,modes_labels,mode_i,trig_value):
    #Given an S matrix computes the correlation/scattirng graph
    #INPUT:
    # S:            scattering matrix (big S, both modes and antimodes)
    # modes_labels: vector containing labels of each modes
    # trig_value:   threshold used to choose if two modes are connected or not
    #OUTPUT:
    # Gi:          the networkX single node graph

    #3pmp-case bckgnd and 0-ref for dB threshold
    S0exp_ref = 0.00035796379677849094
    background = 1.5060476433580897e-06
    #bckgnd_dB = dB(background / S0exp_ref)
    bckgnd_dB = -60  # [dB]             #General bckground level at -60dB

    # Extract small S
    Snum = extract_small_S(S)
    Snum_abs = np.abs(Snum)
    Snum_ang = np.angle(Snum)

    # Graph single input node i
    nmodes = len(modes_labels)
    lab_i = modes_labels[mode_i]
    Scolumn_i = dB(Snum_abs[:, mode_i] + 10**(bckgnd_dB/20))
    nodes_Gi = [lab_i]
    Gi = nx.Graph()
    for j in range(nmodes):
        if (Scolumn_i[j] >= trig_value):
            if (j != mode_i):
                lab_j = modes_labels[j]
                nodes_Gi = np.concatenate((nodes_Gi, [lab_j]))
                Gi.add_edge(lab_i, lab_j)
    return Gi

def extract_singlenode_GifromSmall_S(S,modes_labels,mode_i,trig_value):
    #Given an S matrix computes the correlation/scattirng graph
    #INPUT:
    # S:            scattering matrix (big S, both modes and antimodes)
    # modes_labels: vector containing labels of each modes
    # trig_value:   threshold used to choose if two modes are connected or not
    #OUTPUT:
    # Gi:          the networkX single node graph

    #3pmp-case bckgnd and 0-ref for dB threshold
    S0exp_ref = 0.00035796379677849094
    background = 1.5060476433580897e-06
    #bckgnd_dB = dB(background / S0exp_ref)
    bckgnd_dB = -60  # [dB]             #General bckground level at -60dB

    # Extract small S
    Snum = S
    Snum_abs = np.abs(Snum)
    Snum_ang = np.angle(Snum)

    # Graph single input node i
    nmodes = len(modes_labels)
    lab_i = modes_labels[mode_i]
    Scolumn_i = dB(Snum_abs[:, mode_i] + 10**(bckgnd_dB/20))
    nodes_Gi = [lab_i]
    Gi = nx.Graph()
    for j in range(nmodes):
        if (Scolumn_i[j] >= trig_value):
            if (j != mode_i):
                lab_j = modes_labels[j]
                nodes_Gi = np.concatenate((nodes_Gi, [lab_j]))
                Gi.add_edge(lab_i, lab_j)
    return Gi


def compute_nullifiers(G,modes_labels,xp):
    Nxp_comp, Ndata = xp.shape
    nmodes = len(modes_labels)
    #Def. of nullifiers mean and variance
    Null_meas=np.zeros((nmodes,Ndata))          #Nullifiers measures
    Nullfer=np.zeros(nmodes)
    DeNfer2=np.zeros(nmodes)
    ii=0
    for mode_i in modes_labels:
        i= 2*mode_to_index(mode_i,nmodes) #index of mode_i
        if (G.has_node(mode_i)):
            list_Nj=list(G.neighbors(mode_i))
            print('mode i',mode_i,' neigh.',list_Nj)
            Null_meas[ii, :] = xp[i + 1, :]  #Ni=pi -->  pi=xp[i+1] (xp order x1,p1,x2p2,x3p3,...xi,pi,...) --- First step of Ni = p_i - \sum_j x_j
            for md_j in list_Nj:
                j = 2*mode_to_index(md_j,nmodes) #index of md_j
                Null_meas[ii,:] = Null_meas[ii,:] - xp[j,:]   #pi=xp[i+1]  xj=xp[j] (xp order x1,p1,x2p2,x3p3,...xi,pi,...) --- Ni = p_i - \sum_j x_j
        ii+=1
    #Compute statistic on Nullifier observable measures
    Nullfer=np.mean(Null_meas, axis=1)
    DeNfer2=np.var(Null_meas, axis=1)
    return Nullfer, DeNfer2

def compute_nullifiers_fromVout(G,modes_labels,Vout,xp_mean):
    nmodes = len(modes_labels)
    #Def. of nullifiers mean and variance
    Nullfer=np.zeros(nmodes)
    DeNfer2=np.zeros(nmodes)
    ii=0
    for mode_i in modes_labels:
        i= 2 * mode_to_index(mode_i, nmodes) #index of mode_i
        if (G.has_node(mode_i)):
            list_Nj=list(G.neighbors(mode_i))
            print('mode i',mode_i,' neigh.',list_Nj)
            #Mean
            Nullfer[ii] = xp_mean[i + 1]  #Ni=pi -->  pi=xp[i+1] (xp order x1,p1,x2,p2,x3,p3,...xi,pi,...) --- First step of Ni = p_i - \sum_j x_j
            for md_j in list_Nj:
                j = 2 * mode_to_index(md_j, nmodes) #index of md_j
                Nullfer[ii] = Nullfer[ii] - xp_mean[j]   #pi=xp[i+1]  xj=xp[j] (xp order x1,p1,x2p2,x3p3,...xi,pi,...) --- Ni = p_i - \sum_j x_j
            #Variance
            DeNfer2[ii] = Vout[i + 1, i + 1]  # De pi^2 = Vout[i+1,i+1] (xp order x1,p1,x2,p2,x3,p3,...xi,pi,...) --- (*) DeNi^2 = De pi^2 +\sum_jk x_jx_k - \sum_j (p_ix_j + x_jp_i)
            for md_j in list_Nj:
                for md_k in list_Nj:
                    j = 2 * mode_to_index(md_j, nmodes) #index of md_j
                    k = 2 * mode_to_index(md_k, nmodes)  # index of md_k
                    DeNfer2[ii] = DeNfer2[ii] + Vout[j, k]          #x_jx_k=Vout[j, k]  --- Doing the sum \sum_jk x_jx_k  in (*)
            for md_j in list_Nj:
                j = 2 * mode_to_index(md_j,nmodes) #index of md_j
                DeNfer2[ii] = DeNfer2[ii] - (Vout[i+1, j] + Vout[j,i+1])    #p_i x_j = Vout[i+1, j]  --- Doing the sum \sum_j (p_ix_j + x_jp_i) in (*)
        ii+=1
    # #Compute statistic on Nullifier observable measures
    # Nullfer=np.mean(Null_meas, axis=1)
    # DeNfer2=np.var(Null_meas, axis=1)
    return Nullfer, DeNfer2

def compute_nullifiers_fromVout_insights(G,modes_labels,Vout,xp_mean):
    #Retrocmpatibility function
    Nullfer, DeNfer2, Pi, sumXj, Ni2, Pi2, sumXjXk, sumPiXj, sumXjPi=compute_PX_nullifiers_fromVout(G,modes_labels,Vout,xp_mean)
    return Nullfer, DeNfer2, Pi, sumXj, Ni2, Pi2, sumXjXk, sumPiXj, sumXjPi

def compute_PX_nullifiers(G,modes_labels,Vout,xp_mean, show_details=None):

    if (show_details==None):
        show_details = False
    #Call Nullifiers computation subroutine
    Nullfer, DeNfer2, Pi, sumXj, Ni2, Pi2, sumXjXk, sumPiXj, sumXjPi=compute_PX_nullifiers_fromVout(G,modes_labels,Vout,xp_mean)

    if (show_details==True):
        return Nullfer, DeNfer2, Pi, sumXj, Ni2, Pi2, sumXjXk, sumPiXj, sumXjPi
    else:
        return Nullfer, DeNfer2


def compute_PX_nullifiers_fromVout(G,modes_labels,Vout,xp_mean):
    nmodes = len(modes_labels)
    #Def. of nullifiers mean and variance
    Nullfer=np.zeros(nmodes)
    DeNfer2=np.zeros(nmodes)
    Ni2=np.zeros(nmodes)
    Pi=np.zeros(nmodes)
    sumXj=np.zeros(nmodes)
    sumPiXj = np.zeros(nmodes)
    sumXjPi = np.zeros(nmodes)
    Pi2 = np.zeros(nmodes)
    sumXjXk = np.zeros(nmodes)
    ii=0
    for mode_i in modes_labels:
        i= 2 * mode_to_index(mode_i, nmodes) #index of mode_i
        if (G.has_node(mode_i)):
            list_Nj=list(G.neighbors(mode_i))
            # print('mode i',mode_i,' neigh.',list_Nj)
            #Mean
            Nullfer[ii] = xp_mean[i + 1]  #Ni=pi -->  pi=xp[i+1] (xp order x1,p1,x2,p2,x3,p3,...xi,pi,...) --- First step of Ni = p_i - \sum_j x_j
            Pi[ii]= xp_mean[i + 1]
            for md_j in list_Nj:
                j = 2 * mode_to_index(md_j, nmodes) #index of md_j
                # print('i=', i, ' j=', j, ' mdi', mode_i, ' mdk', md_j)
                sumXj[ii]=sumXj[ii] + xp_mean[j]    #pi=xp[i+1]  xj=xp[j] (xp order x1,p1,x2p2,x3p3,...xi,pi,...) --- Ni = p_i - \sum_j x_j
            Nullfer[ii] = Pi[ii] - sumXj[ii]
            #Variance
            Pi2[ii] = Vout[i + 1, i + 1]      # pi^2 = Vout[i+1,i+1] (xp order x1,p1,x2,p2,x3,p3,...xi,pi,...) --- (*) Ni^2 = pi^2 +\sum_jk x_jx_k - \sum_j (p_ix_j + x_jp_i)
            # print('mode i', mode_i, ' neigh.', list_Nj)
            for md_j in list_Nj:
                for md_k in list_Nj:
                    j = 2 * mode_to_index(md_j, nmodes)      #index of md_j
                    k = 2 * mode_to_index(md_k, nmodes)      # index of md_k
                    # print('j=', j, ' k=', k,' mdj',md_j,' mdk',md_k)
                    sumXjXk[ii] = sumXjXk[ii] + Vout[j, k]   #x_jx_k=Vout[j, k]  --- Doing the sum \sum_jk x_jx_k  in (*)
            for md_j in list_Nj:
                j = 2 * mode_to_index(md_j,nmodes)           #index of md_j
                sumPiXj[ii] = sumPiXj[ii] + Vout[i+1, j]     #p_i x_j = Vout[i+1, j]  --- Doing the sum \sum_j (p_ix_j + x_jp_i) in (*)
                sumXjPi[ii] = sumXjPi[ii] + Vout[j,i+1]
                # print('mdi=', mode_i, ' mdj=', md_j, 'pixj', Vout[i+1, j] , 'xjpi', Vout[i+1, j] )
            # print('mdi=', mode_i, ' mdj=', md_j,'pixj',sumPiXj[ii],'xjpi',sumXjPi[ii])
            Ni2[ii] = Pi2[ii] + sumXjXk[ii] - (sumPiXj[ii] + sumXjPi[ii])  # Ni^2 = pi^2 +\sum_jk x_jx_k - \sum_j (p_ix_j + x_jp_i)
            DeNfer2[ii] = Ni2[ii] - Nullfer[ii]**2                         # DeNi^2= Ni^2 - <Ni>^2
        ii+=1

    return Nullfer, DeNfer2, Pi, sumXj, Ni2, Pi2, sumXjXk, sumPiXj, sumXjPi

def compute_Ni_h(mode_i,list_Nj,list_hj, V,xp_mean,nmodes, sigmaV=None, show_unc=None, show_details=None):
    if (sigmaV is None):
        sigmaV=np.zeros(V.shape)
    if (show_unc==None):
        show_unc=False
    if (show_details==None):
        show_details = False
    if (len(list_Nj)!=len(list_hj)):
        print('ERROR! list_Nj and list_hj must have same lenght.')
        Nullfer=-1
        DeNfer2=-1
        return Nullfer, DeNfer2

    #Nullifier Computation
    # Def. of nullifiers mean and variance
    Nullfer = 0
    DeNfer2 = 0
    Ni2 = 0
    Pi = 0
    sumXj = 0
    sumPiXj = 0
    sumXjPi = 0
    Pi2 = 0
    sumXjXk = 0

    #Uncertainties
    sigmaPi2=0
    sigmaXjXk2=0
    sigmaPiXj2=0
    sigmaNi2=0

    i = 2 * mode_to_index(mode_i, nmodes)  # index of mode_i
    # Mean
    Nullfer = xp_mean[i + 1]  # Ni=pi -->  pi=xp[i+1] (xp order x1,p1,x2,p2,x3,p3,...xi,pi,...) --- First step of Ni = p_i - \sum_j h_jx_j
    Pi = xp_mean[i + 1]
    jj=0
    for md_j in list_Nj:
        j = 2 * mode_to_index(md_j, nmodes)  # index of md_j
        hj=list_hj[jj]
        sumXj = sumXj + hj*xp_mean[j]  # pi=xp[i+1]  xj=xp[j] (xp order x1,p1,x2p2,x3p3,...xi,pi,...) --- Ni = p_i - \sum_j h_jx_j
        jj+=1
    Nullfer = Pi - sumXj
    # Variance pi^2
    Pi2 = V[i + 1, i + 1]  # pi^2 = V[i+1,i+1] (xp order x1,p1,x2,p2,x3,p3,...xi,pi,...) --- (*) Ni^2 = pi^2 +\sum_jk h_jh_k x_jx_k - \sum_j (p_i h_jx_j + h_jx_jp_i)

    # Uncertainty pi^2
    sigmaPi2= sigmaV[i + 1, i + 1]**2

    # Mixed terms:
    jj = 0
    for md_j in list_Nj:
        kk = 0
        for md_k in list_Nj:
            j = 2 * mode_to_index(md_j, nmodes)  # index of md_j
            k = 2 * mode_to_index(md_k, nmodes)  # index of md_k
            hj = list_hj[jj]
            hk = list_hj[kk]
            # print('j=', j, ' k=', k,' mdj',md_j,' mdk',md_k)
            sumXjXk = sumXjXk + hj*hk*V[j, k]  # h_jx_j h_kx_k = h_j*h_k*V[j, k]  --- Doing the sum \sum_jk h_jh_k x_jx_k  in (*)

            # Uncertainty
            sigmaXjXk2 = sigmaXjXk2 + sigmaV[j, k]**2
            kk += 1
        jj += 1
    jj = 0
    for md_j in list_Nj:
        j = 2 * mode_to_index(md_j, nmodes)  # index of md_j
        hj = list_hj[jj]
        sumPiXj = sumPiXj + hj*V[i + 1, j]  # p_i h_jx_j = h_j*V[i+1, j]  --- Doing the sum \sum_j (p_i h_jx_j + h_jx_jp_i) in (*)
        sumXjPi = sumXjPi + hj*V[j, i + 1]

        # Uncertainty
        sigmaPiXj2 = sigmaPiXj2 + sigmaV[i + 1, j] ** 2 + sigmaV[j, i + 1] ** 2
        jj += 1
        # print('mdi=', mode_i, ' mdj=', md_j, 'pixj', V[i+1, j] , 'xjpi', V[i+1, j] )
    # print('mdi=', mode_i, ' mdj=', md_j,'pixj',sumPiXj,'xjpi',sumXjPi)
    Ni2 = Pi2 + sumXjXk - (sumPiXj + sumXjPi)  # Ni^2 = pi^2 +\sum_jk (h_jh_k x_jx_k) - \sum_j (p_i h_jx_j + h_jx_j p_i)
    DeNfer2 = Ni2 - Nullfer ** 2  # DeNi^2= Ni^2 - <Ni>^2

    # Nullifier Uncertainty: sqrt( sigmaPi2^2 + \sum_{jk} sigmaXjXk^2 + \sum_j (sigmaXjPi^2 + sigmaPiXj^2))
    sigmaNi2 = np.sqrt( sigmaPi2 + sigmaXjXk2 + sigmaPiXj2 )

    if (show_details==True):
        if (show_unc==True):
            return Nullfer, DeNfer2, Pi, sumXj, Ni2, Pi2, sumXjXk, sumPiXj, sumXjPi, sigmaNi2
        else:
            return Nullfer, DeNfer2, Pi, sumXj, Ni2, Pi2, sumXjXk, sumPiXj, sumXjPi
    else:
        if (show_unc == True):
            return Nullfer, DeNfer2, sigmaNi2
        else:
            return Nullfer, DeNfer2

def int2bin(x, bits):
    return np.array([int(i) for i in bin(x)[2:].zfill(bits)])

def compute_PP_nullifiers_fromVout(G,modes_labels,Vout,xp_mean):
    nmodes = len(modes_labels)
    #Def. of nullifiers mean and variance
    Nullfer=np.zeros(nmodes)
    DeNfer2=np.zeros(nmodes)
    Ni2=np.zeros(nmodes)
    Pi=np.zeros(nmodes)
    sumPj=np.zeros(nmodes)
    sumPiPj = np.zeros(nmodes)
    sumPjPi = np.zeros(nmodes)
    Pi2 = np.zeros(nmodes)
    sumPjPk = np.zeros(nmodes)
    ii=0
    for mode_i in modes_labels:
        i= 2 * mode_to_index(mode_i, nmodes) #index of mode_i
        if (G.has_node(mode_i)):
            list_Nj=list(G.neighbors(mode_i))
            # print('mode i',mode_i,' neigh.',list_Nj)
            #Mean
            Nullfer[ii] = xp_mean[i + 1]  #Ni=pi -->  pi=xp[i+1] (xp order x1,p1,x2,p2,x3,p3,...xi,pi,...) --- First step of Ni = p_i - \sum_j p_j
            Pi[ii]= xp_mean[i + 1]
            for md_j in list_Nj:
                j = 2 * mode_to_index(md_j, nmodes) #index of md_j
                # print('i=', i, ' j=', j, ' mdi', mode_i, ' mdk', md_j)
                sumPj[ii]=sumPj[ii] + xp_mean[j+1]    #pi=xp[i+1]  pj=xp[j+1] (xp order x1,p1,x2p2,x3p3,...xi,pi,...) --- Ni = p_i - \sum_j p_j
            Nullfer[ii] = Pi[ii] - sumPj[ii]
            #Variance
            Pi2[ii] = Vout[i + 1, i + 1]      # pi^2 = Vout[i+1,i+1] (xp order x1,p1,x2,p2,x3,p3,...xi,pi,...) --- (*) Ni^2 = pi^2 +\sum_jk x_jx_k - \sum_j (p_ip_j + p_jp_i)
            # print('mode i', mode_i, ' neigh.', list_Nj)
            for md_j in list_Nj:
                for md_k in list_Nj:
                    j = 2 * mode_to_index(md_j, nmodes)      #index of md_j
                    k = 2 * mode_to_index(md_k, nmodes)      # index of md_k
                    # print('j=', j, ' k=', k,' mdj',md_j,' mdk',md_k)
                    sumPjPk[ii] = sumPjPk[ii] + Vout[j+1, k+1]   #p_jp_k=Vout[j+1, k+1]  --- Doing the sum \sum_jk p_jp_k  in (*)
            for md_j in list_Nj:
                j = 2 * mode_to_index(md_j,nmodes)           #index of md_j
                sumPiPj[ii] = sumPiPj[ii] + Vout[i+1, j+1]     #p_i x_j = Vout[i+1, j+1]  --- Doing the sum \sum_j (p_ip_j + p_jp_i) in (*)
                sumPjPi[ii] = sumPjPi[ii] + Vout[j+1, i+1]
                # print('mdi=', mode_i, ' mdj=', md_j, 'pipj', Vout[i+1, j+1] , 'xpjpi', Vout[i+1, j+1] )
            # print('mdi=', mode_i, ' mdj=', md_j,'pipj',sumPiPj[ii],'xjpi',sumPjPi[ii])
            Ni2[ii] = Pi2[ii] + sumPjPk[ii] - (sumPiPj[ii] + sumPjPi[ii])  # Ni^2 = pi^2 +\sum_jk p_jp_k - \sum_j (p_ip_j + p_jp_i)
            DeNfer2[ii] = Ni2[ii] - Nullfer[ii]**2                         # DeNi^2= Ni^2 - <Ni>^2
        ii+=1

    return Nullfer, DeNfer2, Pi, sumPj, Ni2, Pi2, sumPjPk, sumPiPj, sumPjPi

def compute_XX_nullifiers_fromVout(G,modes_labels,Vout,xp_mean):
    nmodes = len(modes_labels)
    #Def. of nullifiers mean and variance
    Nullfer=np.zeros(nmodes)
    DeNfer2=np.zeros(nmodes)
    Ni2=np.zeros(nmodes)
    Xi=np.zeros(nmodes)
    sumXj=np.zeros(nmodes)
    sumXiXj = np.zeros(nmodes)
    sumXjXi = np.zeros(nmodes)
    Xi2 = np.zeros(nmodes)
    sumXjXk = np.zeros(nmodes)
    ii=0
    for mode_i in modes_labels:
        i= 2 * mode_to_index(mode_i, nmodes) #index of mode_i
        if (G.has_node(mode_i)):
            list_Nj=list(G.neighbors(mode_i))
            # print('mode i',mode_i,' neigh.',list_Nj)
            #Mean
            Nullfer[ii] = xp_mean[i]  #Ni=xi -->  xi=xp[i] (xp order x1,p1,x2,p2,x3,p3,...xi,pi,...) --- First step of Ni = x_i - \sum_j x_j
            Xi[ii]= xp_mean[i]
            for md_j in list_Nj:
                j = 2 * mode_to_index(md_j, nmodes) #index of md_j
                # print('i=', i, ' j=', j, ' mdi', mode_i, ' mdk', md_j)
                sumXj[ii]=sumXj[ii] + xp_mean[j]    #xi=xp[i]  xj=xp[j] (xp order x1,p1,x2p2,x3p3,...xi,pi,...) --- Ni = x_i - \sum_j x_j
            Nullfer[ii] = Xi[ii] - sumXj[ii]
            #Variance
            Xi2[ii] = Vout[i, i]      # xi^2 = Vout[i,i] (xp order x1,p1,x2,p2,x3,p3,...xi,pi,...) --- (*) Ni^2 = xi^2 +\sum_jk x_jx_k - \sum_j (x_ix_j + x_jx_i)
            # print('mode i', mode_i, ' neigh.', list_Nj)
            for md_j in list_Nj:
                for md_k in list_Nj:
                    j = 2 * mode_to_index(md_j, nmodes)      # index of md_j
                    k = 2 * mode_to_index(md_k, nmodes)      # index of md_k
                    # print('j=', j, ' k=', k,' mdj',md_j,' mdk',md_k)
                    sumXjXk[ii] = sumXjXk[ii] + Vout[j, k]   #x_jx_k=Vout[j, k]  --- Doing the sum \sum_jk x_jx_k  in (*)
            for md_j in list_Nj:
                j = 2 * mode_to_index(md_j,nmodes)           #index of md_j
                sumXiXj[ii] = sumXiXj[ii] + Vout[i, j]     #x_i x_j = Vout[i, j]  --- Doing the sum \sum_j (x_ix_j + x_jx_i) in (*)
                sumXjXi[ii] = sumXjXi[ii] + Vout[j, i]
                # print('mdi=', mode_i, ' mdj=', md_j, 'pipj', Vout[i+1, j+1] , 'xpjpi', Vout[i+1, j+1] )
            # print('mdi=', mode_i, ' mdj=', md_j,'pipj',sumPiPj[ii],'xjpi',sumPjPi[ii])
            Ni2[ii] = Xi2[ii] + sumXjXk[ii] - (sumXiXj[ii] + sumXjXi[ii])  # Ni^2 = xi^2 +\sum_jk x_jx_k - \sum_j (x_ix_j + x_jx_i)
            DeNfer2[ii] = Ni2[ii] - Nullfer[ii]**2                         # DeNi^2= Ni^2 - <Ni>^2
        ii+=1

    return Nullfer, DeNfer2, Xi, sumXj, Ni2, Xi2, sumXjXk, sumXiXj, sumXjXi

def compute_nullifiers_plus(G,modes_labels,xp): #definition with the plus sign: p + x
    Nxp_comp, Ndata = xp.shape
    nmodes = len(modes_labels)
    #Def. of nullifiers mean and variance
    Null_meas=np.zeros((nmodes,Ndata))          #Nullifiers measures
    Nullfer=np.zeros(nmodes)
    DeNfer2=np.zeros(nmodes)
    ii=0
    for mode_i in modes_labels:
        i= 2*mode_to_index(mode_i,nmodes) #index of mode_i
        if (G.has_node(mode_i)):
            list_Nj=G.neighbors(mode_i)
            #print('mode i',mode_i,' neigh.',list(list_Nj))
            Null_meas[ii, :] = xp[i + 1, :]  #Ni=pi -->  pi=xp[i+1] (xp order x1,p1,x2p2,x3p3,...xi,pi,...) --- First step of Ni = p_i + \sum_j x_j
            for md_j in list_Nj:
                j = 2*mode_to_index(md_j,nmodes) #index of md_j
                Null_meas[ii,:] = Null_meas[ii,:] + xp[j,:]   #pi=xp[i+1]  xj=xp[j] (xp order x1,p1,x2p2,x3p3,...xi,pi,...) --- Ni = p_i + \sum_j x_j
        ii+=1
    #Compute statistic on Nullifier observable measures
    Nullfer=np.mean(Null_meas, axis=1)
    DeNfer2=np.var(Null_meas, axis=1)
    return Nullfer, DeNfer2

def compute_nullifiers_q(G,modes_labels,xp):
    Nxp_comp, Ndata = xp.shape
    nmodes = len(modes_labels)
    #Def. of nullifiers mean and variance
    Null_meas=np.zeros((nmodes,Ndata))          #Nullifiers measures
    Nullfer=np.zeros(nmodes)
    DeNfer2=np.zeros(nmodes)
    ii=0
    for mode_i in modes_labels:
        i = 2*mode_to_index(mode_i, nmodes)  # index of mode_i
        if (G.has_node(mode_i)):
            list_Nj=G.neighbors(mode_i)
            #print('mode i',mode_i,' neigh.',list(list_Nj))
            Null_meas[ii, :] = xp[i, :]  #Ni=xi -->  xi=xp[i] (xp order x1,p1,x2p2,x3p3,...xi,pi,...) --- First step of Ni = x_i - \sum_j p_j
            for md_j in list_Nj:
                j = 2*mode_to_index(md_j,nmodes) #index of md_j
                Null_meas[ii,:] = Null_meas[ii,:] - xp[j+1,:]   #xi=xp[i]  pj=xp[j+1] (xp order x1,p1,x2p2,x3p3,...xi,pi,...) --- Ni = x_i - \sum_j p_j
        ii+=1
    #Compute statistic on Nullifier observable measures
    Nullfer=np.mean(Null_meas, axis=1)
    DeNfer2=np.var(Null_meas, axis=1)
    return Nullfer, DeNfer2

def get_ellipse_ij(Vij):
    # Get a,b for  Ellipses pi-xj, pi-pj, and xi-xj
    # (x/a)^2 + (y/b)^2 = 1

    #Ellipse pi-xj
    Vpx = Vij[1:2 + 1, 1:2 + 1]
    lpx, Rpx = np.linalg.eigh(Vpx) #sci.linalg.eig(Vpx)

    # Ellipse pi-pj
    Vpp = Vij[1::2 , 1::2 ]
    lpp, Rpp = np.linalg.eigh(Vpp) #sci.linalg.eig(Vpp)

    # Ellipse xi-xj
    Vxx= Vij[0::2, 0::2]
    lxx, Rxx = np.linalg.eigh(Vxx) #sci.linalg.eig(Vxx)
    return np.real(lpx),Rpx,np.real(lpp),Rpp,np.real(lxx),Rxx

def get_ab_from_lofTheta(lambda_vec):
    #INPUT:
    #  lambda_vec: Ntheta x 2 vector of eigenvalues lambda_vec[:,0] and lambda_vec[:,1]  as function of theta.
    #OUTPUT:
    #  a,b: vectors of a and b of the ellipse
    Ntheta, Nl = lambda_vec.shape
    lambdaT=np.zeros((Ntheta, Nl))

    #Order Lambdas
    lambdaT[:,0] = np.max(lambda_vec, axis=1)   # lambdaT[:,0] vector of bigger eigenvalues
    lambdaT[:,1] = np.min(lambda_vec, axis=1)   # lambdaT[:,1] vector of smaller eigenvalues
    a = np.zeros(Ntheta)
    b = np.zeros(Ntheta)
    pointer=0               #start pointing a --to--> lambda0
    a[0] = lambdaT[0, 0]
    b[0] = lambdaT[0, 1]
    theta = 1
    if ((lambdaT[theta, 0] < lambdaT[theta - 1, 0]) and (lambdaT[theta, 0] < lambdaT[theta + 1, 0])):
        switch = True
    else:
        switch = False
    while (theta < Ntheta-1):
        if (switch == True):
            pointer=1-pointer
            switch = False
        a[theta] = lambdaT[theta, pointer]
        b[theta] = lambdaT[theta, 1-pointer]
        if ((lambdaT[theta, 0] < lambdaT[theta - 1, 0]) and (lambdaT[theta, 0] < lambdaT[theta + 1, 0])): #test for next round
            switch = True
        else:
            switch = False
        theta += 1
    #Assign last value
    if (switch == True):
        pointer = 1 - pointer
    a[theta] = lambdaT[theta, pointer]
    b[theta] = lambdaT[theta, 1 - pointer]
    return a, b

def reorder_eig_ellipse(lambda_vec,R_vec):
    #INPUT:
    #  lambda_vec: Ntheta x 2 vector of eigenvalues lambda_vec[:,0] and lambda_vec[:,1]  as function of theta.
    #  R_vec:   Ntheta x 2 x 2: vector of matrices of eigenvectors as a function of theta
    #OUTPUT:
    #  lambT_out: vectors of eigenvalues a (axis 0) and b (axis 1) of the rotating ellipse for all theta
    #  RT_out: vector of matrices of eigenvectors as a function of theta matching the above eigenvalues

    Ntheta, Nl = lambda_vec.shape
    lambdaT=np.zeros((Ntheta, Nl))
    lambT_out = np.zeros((Ntheta, Nl))
    R_T=np.zeros(R_vec.shape)
    RT_out = np.zeros(R_vec.shape)

    #Order Lambdas
    # lambdaT[:,0] vector of bigger eigenvalues
    # lambdaT[:,1] vector of smaller eigenvalues
    for theta in range(Ntheta):
        if ( lambda_vec[theta,0]>=lambda_vec[theta,1] ): #copy as it is
            lambdaT[theta, 0] = lambda_vec[theta, 0]
            lambdaT[theta, 1] = lambda_vec[theta, 1]
        else:   #switch
            lambdaT[theta, 0] = lambda_vec[theta, 1]
            lambdaT[theta, 1] = lambda_vec[theta, 0]
            #switch also eigenvectors (R_vec[theta,:,:] columns)
            R_T[theta, :, 0] = R_vec[theta, :, 1]
            R_T[theta, :, 1] = R_vec[theta, :, 0]
    pointer=0               #start pointing a --to--> lambda0
    lambT_out[0, 0] = lambdaT[0, 0]      #a
    lambT_out[0, 1] = lambdaT[0, 1]      #b
    theta = 1
    if ((lambdaT[theta, 0] < lambdaT[theta - 1, 0]) and (lambdaT[theta, 0] < lambdaT[theta + 1, 0])):
        switch = True
    else:
        switch = False
    while (theta < Ntheta-1):
        if (switch == True):
            pointer=1-pointer
            switch = False
        lambT_out[theta, 0] = lambdaT[theta, pointer]
        lambT_out[theta, 1] = lambdaT[theta, 1-pointer]
        RT_out[theta, :, 0] = R_vec[theta, :, pointer]
        RT_out[theta, :, 1] = R_vec[theta, :, 1-pointer]
        if ((lambdaT[theta, 0] < lambdaT[theta - 1, 0]) and (lambdaT[theta, 0] < lambdaT[theta + 1, 0])): #test for next round
            switch = True
        else:
            switch = False
        theta += 1
    #Assign last value
    if (switch == True):
        pointer = 1 - pointer
    lambT_out[theta, 0] = lambdaT[theta, pointer]
    lambT_out[theta, 1] = lambdaT[theta, 1 - pointer]
    RT_out[theta, :, 0] = R_vec[theta, :, pointer]
    RT_out[theta, :, 1] = R_vec[theta, :, 1 - pointer]
    return lambT_out, RT_out

def test_function(x,omega_i,Delta):
    Np=len(x)
    fcn=np.zeros((Np))
    for i in range(Np):
        if ( ( (omega_i - Delta/2) < x[i] )and( x[i] < (omega_i + Delta/2) ) ):
            fcn[i]=(1 / np.sqrt(np.pi))*np.exp(-1/( (Delta**2)/4 - (x[i]-omega_i)**2 ))
            # 1000 * (1 / np.sqrt(np.pi))
            # print('y ',fcn[i])
        else:
            fcn[i]=0
            # print('n ', fcn[i])
    return fcn

def sinc_function(x,omega_i,T):
    Np=len(x)
    fcn=np.zeros((Np))
    for i in range(Np):
        fcn[i]=np.sin(np.pi*T*(x[i]-omega_i))/(np.pi*T*(x[i]-omega_i))
    return fcn

def is_symplectic(M, print_flag=None):
    #Input: matrix M
    #output: true or false of the symplecticity test
    if ( print_flag == None ):
        print_flag = False
    Nr, Nc=M.shape
    if ( (Nr==Nc) and (Nr % 2==0) ):
        N=int(Nr/2)
        Omg = np.array([[0, 1],
                        [-1, 0]])
        symp = np.kron(np.eye(N), Omg)
        symp2 = M.dot(symp).dot(np.transpose(np.conjugate(M)))  #(1 / 2) *  The 1/2 is from the choice (a + a^*)/sqrt(2)
        # Return test result
        result = np.all(np.round(np.real(symp2)) == symp)
    else: #odd rows or not-square matrices cannot be symplectic
        result = False
        print('warning odd-rows/not-square')
    if (result== False):
        if ( print_flag == True ):
            print_Matrix(symp2)
    return result

def is_physical(M, toll=None, print=None):
    # Input: matrix M
    # output: true or false M +- iOmega >= 0 (positive semidef.)
    if (toll==None):
        toll=0
    if (print==None):
        print=False

    Nr, Nc = M.shape
    if ((Nr == Nc) and (Nr % 2 == 0)):
        N = int(Nr / 2)
        Omg = np.array([[0, 1],
                        [-1, 0]])
        Symp = np.kron(np.eye(N), Omg)
        MTest_p = (M + 1j * 0.5 * Symp)
        MTest_m = (M - 1j * 0.5 * Symp)
        lambM_p, R_p = sci.linalg.eig(MTest_p)
        lambM_m, R_m = sci.linalg.eig(MTest_m)

        # Return test result
        result_plus = np.all(np.real(lambM_p) >= -toll)
        result_minus = np.all(np.real(lambM_m) >= -toll)
        result = result_plus and result_minus
    else:  # odd rows or not-square matrices cannot be symplectic
        result_plus=False
        result_minus = False
        lambM_p=0
        lambM_m=0
        result = False
        print('warning odd-rows/not-square')
    if ( (result == False) and (print== True) ):
        print('M + jOmg>=0:', result_plus)
        print('M + jOmg>=0:', np.real(lambM_p[np.where(np.real(lambM_p) < -toll)]))
        print('M - jOmg>=0:', result_minus)
        print('M - jOmg Eigenval.:', np.real(lambM_m[np.where(np.real(lambM_m) < -toll)]))
    return result

def is_positive(M):
    # Input: matrix M
    # output: true or false if M is positive semidef. M >= 0
    Nr, Nc = M.shape
    if ((Nr == Nc) and (Nr % 2 == 0)):
        N = int(Nr / 2)
        lambM, R = sci.linalg.eig(M)

        # Return test result
        result = np.all(np.real(lambM) >= 0)

    else:  # odd rows or not-square matrices cannot be symplectic
        lambM=0
        result = False
        print('warning odd-rows/not-square')
    # if (result == False):
    #     print('M>=0:',result)
    #     print('M Eigenval.:', np.real(lambM))

    return result

def covFS_to_covN(Vin, omega, Delta, FS2V_ratio=None, R=None):
    hbar=sci.hbar
    if (FS2V_ratio == None):
        FS2V_ratio = 0.45825639139394   #ration FS to Volt
    if (R == None):
        R=50    #ohm
    Nmod=len(omega)
    Vout=np.zeros((2*Nmod,2*Nmod))
    for i in range(Nmod):
        for j in range(Nmod):
            ii=2*i
            jj=2*j
            Vout[ii, jj] = Vin[ii, jj] * (FS2V_ratio ** 2) / (R * hbar * Delta * np.sqrt(omega[i] * omega[j]))    #xx
            Vout[ii, jj + 1] = Vin[ii, jj + 1] * (FS2V_ratio ** 2) / (R * hbar * Delta * np.sqrt(omega[i] * omega[j])) #xp
            Vout[ii + 1, jj] = Vin[ii + 1, jj] * (FS2V_ratio ** 2) / (R * hbar * Delta * np.sqrt(omega[i] * omega[j])) #px
            Vout[ii + 1, jj + 1] = Vin[ii + 1, jj + 1] * (FS2V_ratio ** 2) / (R * hbar * Delta * np.sqrt(omega[i] * omega[j])) #pp
    return Vout


def Msqrt(M):
    #Return the matrix sqM such that sqM^2 = M 
    
    #Diagonalize M  
    d, U = np.linalg.eig(M)
    Udag=np.linalg.inv(U)
    
    # Compute square root eigenvalues of M
    sq_d=np.emath.sqrt(d)
    
    # Compute the sqare root of matrix D (the diagonalized M)
    sqD=np.diag(sq_d)
    
    # Rotate sqD through U to get the sqare root of M
    sqM=U.dot(sqD).dot(Udag)
    return sqM

def square_lattice(mode_labels,Nx):
    #Generate coordinates of a square lattice grid with Nx sites on x direction
    positions = {}
    xx=1
    yy=1
    for lab_ii in mode_labels:
        if (xx==Nx+1):
            xx=1
            yy+=1
        positions[lab_ii]=[xx,yy]
        xx+=1

    return positions


def square_lattice_4SqPumps(mode_labels,Nx):
    #Generate coordinates of a square lattice grid with Nx sites on x direction
    positions = {}
    for lab_ii in mode_labels:
        if lab_ii==0:
            xx=0
            yy=0
        else:
            if ( (lab_ii%2==0) and (lab_ii<0) ) or ( (lab_ii%2!=0) and (lab_ii>0) ):
                #case even<0 or odd>0 : (0),1,-2,3,-4,...
                xx = np.abs(lab_ii) % Nx
                if (xx==0):
                    yy = -np.abs(lab_ii) // Nx
                else:
                    yy = -np.abs(lab_ii) // Nx + 1
            else:
                #case even>0 or odd<0 : ...,4,-3,2,-1,(0)
                xx = ( Nx - np.abs(lab_ii) ) % Nx
                if (xx==0):
                    yy = np.abs(lab_ii) // Nx
                else:
                    yy = np.abs(lab_ii) // Nx + 1
        positions[lab_ii] = [xx, yy]
    return positions

def square_lattice_NxEven(mode_labels,Nx):
    #Generate coordinates of a square lattice grid with Nx sites on x direction
    positions = {}
    for lab_ii in mode_labels:
        if ( (lab_ii%2==0) and (lab_ii<0) ) or ( (lab_ii%2!=0) and (lab_ii>0) ):
            # odd>0 or even<0: 1,-2,3,-4,...  (y goes negative)
            xx = np.abs(lab_ii) % Nx
            if (xx==0):
                xx=Nx
            yy = -np.abs(lab_ii) // Nx - 1
        else:
            # odd<0 or even>0 : ...,4,-3,2,-1  (y goes positive)
            xx = Nx  - np.abs(lab_ii) % Nx  
            if (xx==Nx+1): 
                # print('xx=0 ',lab_ii)
                xx=1
                yy = np.abs(lab_ii) // Nx -1 - 1
            else:
                yy = np.abs(lab_ii) // Nx -1
        # For tilted or not tilted
        xx = xx - yy
        positions[lab_ii] = [xx, yy]
    return positions

def honeyC_lattice(mode_labels,Nx):
    #Generate coordinates of a square lattice grid with Nx sites on x direction
    positions = {}
    dx=(3/4)*np.sqrt(3)/2 #
    dy=1/4
    for lab_ii in mode_labels:
        if ( (lab_ii%2==0) and (lab_ii<0) ) or ( (lab_ii%2!=0) and (lab_ii>0) ):
            # odd>0 or even<0: 1,-2,3,-4,...  (y goes negative)
            xx = np.abs(lab_ii) % Nx
            if (xx==0):
                xx=Nx
            yy = -np.abs(lab_ii) // Nx - 1

        else:
            # odd<0 or even>0 : ...,4,-3,2,-1  (y goes positive)
            xx = Nx  - np.abs(lab_ii) % Nx
            if (xx==Nx+1):
                # print('xx=0 ',lab_ii)
                xx=1
                yy = np.abs(lab_ii) // Nx -1 - 1
            else:
                yy = np.abs(lab_ii) // Nx -1
            
        # For tilted or not tilted lattice (xy by pi/3)
        xx = xx - yy
        xx = xx * dx
        # Shift y position of up (down)
        if ( (lab_ii%2==0) and (lab_ii<0) ) or ( (lab_ii%2!=0) and (lab_ii>0) ):
            if ( yy%2 != 0 ):
                if (lab_ii>0):
                    yy= yy + dy/2
                else:
                    yy= yy - dy/2                
            elif ( yy%2 == 0 ):
                if ( lab_ii<0 ):
                    yy= yy - dy/2
                else:   
                    yy= yy + dy/2
        else:
            if ( yy%2 == 0 ): 
                if( lab_ii>0 ):
                    yy= yy - dy/2
                else:
                    yy= yy + dy/2
            elif ( yy%2 != 0 ):
                if ( lab_ii<0 ):
                    yy= yy + dy/2
                else:
                    yy= yy - dy/2
        # Assign position
        positions[lab_ii] = [xx, yy]
    return positions


def dual_rail(modes_labels,nmodes):
    tt=0
    py=-1
    if (nmodes % 2 == 0):
        nhalf=int(nmodes/2)
    else:
        nhalf=int((nmodes-1)/2)
    modes_labels_inv = np.concatenate((modes_labels[nhalf:nmodes], modes_labels[0:nhalf] ))
    modes_labels_pos = modes_labels[nhalf:nmodes]
    positions = {}
    for lab_ii in modes_labels_pos:
        if (lab_ii==0):
            positions[lab_ii]=[tt, 0]
        else:
            positions[lab_ii]=[tt, 1]
            positions[-lab_ii]=[tt, -1]
            # if (lab_ii % 8 == 0):
            #     pos_ladd[lab_ii] = positions[-lab_ii]
            #     pos_ladd[-lab_ii] = positions[lab_ii]
            # else:
            #     pos_ladd[lab_ii] = positions[lab_ii]
            #     pos_ladd[-lab_ii] = positions[-lab_ii]
            # if ((lab_ii + 2) % 8 == 0):
            #     pos_ladd2[lab_ii] = positions[-lab_ii]
            #     pos_ladd2[-lab_ii] = positions[lab_ii]
            # else:
            #     pos_ladd2[lab_ii] = positions[lab_ii]
            #     pos_ladd2[-lab_ii] = positions[-lab_ii]
        tt+=1

    return positions

def dual_rail_odd(modes_labels,nmodes):
    tt=0
    py=-1
    if (nmodes % 2 == 0):
        nhalf=int(nmodes/2)
    else:
        nhalf=int((nmodes-1)/2)
    modes_labels_inv = np.concatenate((modes_labels[nhalf:nmodes], modes_labels[0:nhalf] ))
    modes_labels_pos = modes_labels[nhalf:nmodes]
    positions = {}
    for lab_ii in modes_labels_pos:
        if (lab_ii==0):
            positions[lab_ii]=[tt, 0]
        else:
            positions[lab_ii]=[tt, 1]
            positions[-lab_ii]=[tt, -1]
            # if (lab_ii % 8 == 0):
            #     pos_ladd[lab_ii] = positions[-lab_ii]
            #     pos_ladd[-lab_ii] = positions[lab_ii]
            # else:
            #     pos_ladd[lab_ii] = positions[lab_ii]
            #     pos_ladd[-lab_ii] = positions[-lab_ii]
            # if ((lab_ii + 2) % 8 == 0):
            #     pos_ladd2[lab_ii] = positions[-lab_ii]
            #     pos_ladd2[-lab_ii] = positions[lab_ii]
            # else:
            #     pos_ladd2[lab_ii] = positions[lab_ii]
            #     pos_ladd2[-lab_ii] = positions[-lab_ii]
        tt+=1

    # Positions Odd Double-Ladder (center graph k=4,-4)
    mlabel_odd3tomax = [a for a in range(3, nhalf + 1, 4)]
    mlabel_odd1tomax = [a for a in range(1, nhalf + 1, 4)]
    mlabel_oddmmaxto1 = mlabel_odd1tomax[::-1]
    mlabel_odd_by4 = np.concatenate((mlabel_oddmmaxto1, mlabel_odd3tomax))

    mlabel_upRight = np.zeros(len(mlabel_odd3tomax))
    ii = 0
    for lab_ii in mlabel_odd3tomax:
        if (ii % 2 == 0):
            mlabel_upRight[ii] = lab_ii
        else:
            mlabel_upRight[ii] = -lab_ii
        ii += 1
    mlabel_upLeft = np.zeros(len(mlabel_odd1tomax))
    ii = 0
    for lab_ii in mlabel_odd1tomax:
        if (ii % 2 == 0):
            mlabel_upLeft[ii] = lab_ii
        else:
            mlabel_upLeft[ii] = -lab_ii
        ii += 1
    mlabel_dwnLeft = -mlabel_upLeft

    pos_doubleOddLad = {}
    tt = 0
    for lab_ii in mlabel_upRight:
        pos_doubleOddLad[lab_ii] = [tt, 0.5]
        pos_doubleOddLad[-lab_ii] = [tt, -0.5]
        tt += 1
    tt = -1
    for lab_ii in mlabel_upLeft:
        pos_doubleOddLad[lab_ii] = [tt, 0.5]
        pos_doubleOddLad[-lab_ii] = [tt, -0.5]
        tt -= 1

    positions=pos_doubleOddLad

    return positions

## DATA SAVING FUNCTIONS

def save_data(folder, file, datagroup_label, data, dtype, data_name_str, data_attr_str,overwrite):
    # folder:   folder path in wich the HDF5 data file is to be saved
    # file:     name of the HDF5 file
    # datagroup_label:   group name (file section/folder) eg. 'experiment 1'
    # data: data to be   saved (e.g. vector, variable or anything)
    # data_handle_str:   name of the saved variable (string)
    # data_attr_str:     attribute/meta-data and/or any descriptive info related to the data (string)
    # ovewrite:          flag to overwrite data if present (yes if 1 (default), no if 0)
    #Check and set default
    overwrite=overwrite or 1

    if not os.path.isdir(folder):
        os.makedirs(folder)

    # Open the save file (.hdf5) in append mode
    with h5py.File(os.path.join(folder, file), "a") as savefile:
        # String as handles
        data_handle_str = "{}/" + data_name_str
        data_handle_str=data_handle_str.format(datagroup_label)
        # Check if the group exist (if not creates a new one)
        local_group=savefile.require_group(datagroup_label)
        if data_name_str not in local_group.keys():
            # Write data to datasets
            local_group.create_dataset(data_name_str, (np.shape(data)),
                                    dtype=dtype, data=data)
            # Write dataset attributes
            savefile[data_handle_str].attrs["Meta-Data"] = data_attr_str
        else:
            if (overwrite==1):
                #delete old
                del local_group[data_name_str]
                # Write data to datasets
                local_group.create_dataset(data_name_str, (np.shape(data)),
                                           dtype=dtype, data=data)
                # Write dataset attributes
                savefile[data_handle_str].attrs["Meta-Data"] = data_attr_str

        savefile.close()


def load_data(folder,file, datagroup_label):
    # Open hdf5 file
    with h5py.File(os.path.join(folder, file), "r") as HDFfile:
        data=HDFfile[datagroup_label]

    return data


def load_dataset(folder,file, datagroup_label, data_label):
    # Open hdf5 file
    with h5py.File(os.path.join(folder, file), "r") as HDFfile:
        # Data
        dset= np.asarray(HDFfile[datagroup_label][data_label])

    return dset

def load_singledata(folder,file, datagroup_label, data_label):
    # Open hdf5 file
    with h5py.File(os.path.join(folder, file), "r") as dataset:
        # Data
        dset= np.asarray(dataset[datagroup_label][data_label])

    return dict(dset)

def load_ExpData(file_, idx_str_):
    # Open hdf5 file
    with h5py.File(file_, "r") as dataset:
        # Data
        return dict(df=np.asarray(dataset[idx_str_]["df"]),
                    freq_sig=np.asarray(dataset[idx_str_]["freq sig"]),
                    freq_param=np.asarray(dataset[idx_str_]["freq param pumps"]),
                    amp_param=np.asarray(dataset[idx_str_]["amp param pumps"]),
                    phase_param=np.asarray(dataset[idx_str_]["phase param pumps"]),
                    freq_fc=np.asarray(dataset[idx_str_]["freq fc pumps"]),
                    amp_fc=np.asarray(dataset[idx_str_]["amp fc pumps"]),
                    phase_fc=np.asarray(dataset[idx_str_]["phase fc pumps"]),
                    USB=np.asarray(dataset[idx_str_]["USB"]),
                    freq_param_center=dataset[idx_str_].attrs["fp_center"],
                    )
    

def load_EntData(file_, idx_str_):
    # Open hdf5 file
    with h5py.File(file_, "r") as dataset:
        # Data
        return dict(USBoff=np.asarray(dataset[idx_str_]["USB OFF"]),
                    USBon=np.asarray(dataset[idx_str_]["USB ON"]),
                    freq_comb=np.asarray(dataset[idx_str_]["freq comb"]),
                    )

def load_EntTimeData(file_, idx_str_):
    # Open hdf5 file
    with h5py.File(file_, "r") as dataset:
        # Data
        return dict(USBon=np.asarray(dataset[idx_str_]["USB ON"]),
                    freq_comb=np.asarray(dataset[idx_str_]["freq comb"]),
                    )

def load_CovData(file_, idx_str_):
    # Open hdf5 file
    with h5py.File(file_, "r") as dataset:
        # print(dataset[idx_str_].keys())
        # Data
        return dict(Vexp_off=np.asarray(dataset[idx_str_]["Vexp off"]),
                    Vexp_on=np.asarray(dataset[idx_str_]["Vexp on"]),
                    Vq_off=np.asarray(dataset[idx_str_]["Vq off"]),
                    Vq_on=np.asarray(dataset[idx_str_]["Vq on"]),
                    Vp_off=np.asarray(dataset[idx_str_]["Vp off"]),
                    Vp_on=np.asarray(dataset[idx_str_]["Vp on"]),
                    sVp_off=np.asarray(dataset[idx_str_]["sVp off"]),
                    sVp_on=np.asarray(dataset[idx_str_]["sVp on"]),
                    xp0_mean=np.asarray(dataset[idx_str_]["meanq off"]),
                    xp_mean=np.asarray(dataset[idx_str_]["meanq on"]),
                    )

def load_HDFdata(file_, idx_str_,data_name):
    # Open hdf5 file
    with h5py.File(file_, "r") as dataset:
        # print(dataset[idx_str_].keys())
        data=np.asarray(dataset[idx_str_][data_name])
        return data

def load_PlanckData(file_, idx_str_):
    # Open hdf5 file
    with h5py.File(file_, "r") as dataset:
        # Data
        return dict(LSB=np.asarray(dataset[idx_str_]["LSB"]),
                    USB=np.asarray(dataset[idx_str_]["USB"]),
                    freq_comb=np.asarray(dataset[idx_str_]["freq comb"]),
                    )


##### ----- Routines for Ai aI ----- #####
def physical_param():
    #Definition of frequencies of the system
    f0 = 4.2  # [GHz] Resonance frequency of the JPA
    omega0 = 2 * np.pi * f0
    Delta_f = 0.1e-3  # [GHz] Modes spacing (typically 100KHz)
    Delta = 2 * np.pi * Delta_f
    return omega0, Delta

def fit_parameters():
    gp_tune = 54
    gamma_tune = 10*gp_tune
    return gp_tune, gamma_tune

def fit_parameters_3pmp():
    gp_tune = 54 #849.2462311557789
    gamma_tune = 533.33333 #1993.9698492462312
    return gp_tune, gamma_tune
def fit_parameters_2pmp():
    gp_tune = 74 #665.1515151515151
    gamma_tune = 747.47474747 #1397.878787878788
    return gp_tune, gamma_tune
def fit_parameters_1pmp():
    gp_tune = 72 #47.27272727272727
    gamma_tune = 19.09090909 #24.0
    return gp_tune, gamma_tune

def compute_S_AiaI(nmodes, gp0, phi_p, omega_p):
    # Compute the small S for Ai all'Italiana (S already normalized with the 0 pump case)

    # Physical parameters and Mode Basis definition
    omega0, Delta = physical_param()
    gp_tune, gamma_tune=fit_parameters()
    # gp_tune = 200 #849.2462311557789
    # gamma_tune = 200*2.4 #1993.9698492462312

    modes_freq, modes_labels, allmodes_freq = generate_freq_vectors(nmodes, omega0, Delta)
    # Dissipation Rates
    gamma_int = 0.
    gamma_ext = 2 * np.pi * 100 * (10 ** 6) / (10 ** 9)  # [GHz]
    gamma0_ext = gamma_ext * gamma_tune
    gamma = gamma_int + gamma0_ext

    # Compute complex Pump Strength
    Npumps = len(gp0)
    gp = np.zeros(Npumps, dtype=complex)
    for pp in range(Npumps):
        gp[pp] = gp_tune * gp0[pp] * np.exp(1j * phi_p[pp])

    # Call fcn to compute M and Minv
    M, M_inv = compute_M(omega0, nmodes, allmodes_freq, modes_freq, gamma, Npumps, gp, omega_p)

    # Compute Scattering Matrix S
    Id = np.identity(2 * nmodes)
    K = np.identity(2 * nmodes) * np.sqrt(gamma0_ext)
    Saa = 1j * K.dot(M_inv).dot(K) - Id

    # Compute the reference (zero-pump case)
    Npump_ref = 1
    g0ref = np.zeros((Npump_ref), dtype=complex)
    omega_pref = np.zeros((Npump_ref))
    omega_pref[0] = Delta * 2000
    M0ref, M0ref_inv = compute_M(omega0, nmodes, allmodes_freq, modes_freq, gamma, 1, g0ref, omega_pref)
    S0aa_ref = 1j * K.dot(M0ref_inv).dot(K) - Id
    S0a_ref = extract_small_S(S0aa_ref)
    S0num_ref = np.mean(np.abs(np.diag(S0a_ref)))  # Compute the mean of the diagonal elements'abs valu

    # Extract small S and normalize it with zero-pump case
    S = extract_small_S(Saa) / S0num_ref

    return S

def compute_S_3pmp(nmodes, gp0, phi_p, omega_p):
    # Compute the small S for Ai all'Italiana (S already normalized with the 0 pump case)

    # Physical parameters and Mode Basis definition
    omega0, Delta = physical_param()
    # gp_tune, gamma_tune=fit_parameters_3pmp()
    gp_tune = 1 #849.2462311557789
    gamma_tune = gp_tune*2.4 #1993.9698492462312

    modes_freq, modes_labels, allmodes_freq = generate_freq_vectors(nmodes, omega0, Delta)
    # Dissipation Rates
    gamma_int = 0.
    gamma_ext = 2 * np.pi * 100 * (10 ** 6) / (10 ** 9)  # [GHz]
    gamma0_ext = gamma_ext * gamma_tune
    gamma = gamma_int + gamma0_ext

    # Compute complex Pump Strength
    Npumps = len(gp0)
    gp = np.zeros(Npumps, dtype=complex)
    for pp in range(Npumps):
        gp[pp] = gp_tune * gp0[pp] * np.exp(1j * phi_p[pp])

    # Call fcn to compute M and Minv
    M, M_inv = compute_M(omega0, nmodes, allmodes_freq, modes_freq, gamma, Npumps, gp, omega_p)

    # Compute Scattering Matrix S
    Id = np.identity(2 * nmodes)
    K = np.identity(2 * nmodes) * np.sqrt(gamma0_ext)
    Saa = 1j * K.dot(M_inv).dot(K) - Id

    # Compute the reference (zero-pump case)
    Npump_ref = 1
    g0ref = np.zeros((Npump_ref), dtype=complex)
    omega_pref = np.zeros((Npump_ref))
    omega_pref[0] = Delta * 2000
    M0ref, M0ref_inv = compute_M(omega0, nmodes, allmodes_freq, modes_freq, gamma, 1, g0ref, omega_pref)
    S0aa_ref = 1j * K.dot(M0ref_inv).dot(K) - Id
    S0a_ref = extract_small_S(S0aa_ref)
    S0num_ref = np.mean(np.abs(np.diag(S0a_ref)))  # Compute the mean of the diagonal elements'abs valu

    # Extract small S and normalize it with zero-pump case
    S = extract_small_S(Saa) / S0num_ref

    return S

def compute_bigS_3pmp(nmodes, gp0, phi_p, omega_p):
    # Compute the small S for Ai all'Italiana (S already normalized with the 0 pump case)

    # Physical parameters and Mode Basis definition
    omega0, Delta = physical_param()
    gp_tune, gamma_tune=fit_parameters_3pmp()
    # gp_tune = 200 #849.2462311557789
    # gamma_tune = 200*2.4 #1993.9698492462312

    modes_freq, modes_labels, allmodes_freq = generate_freq_vectors(nmodes, omega0, Delta)
    # Dissipation Rates
    gamma_int = 0.
    gamma_ext = 2 * np.pi * 100 * (10 ** 6) / (10 ** 9)  # [GHz]
    gamma0_ext = gamma_ext * gamma_tune
    gamma = gamma_int + gamma0_ext

    # Compute complex Pump Strength
    Npumps = len(gp0)
    gp = np.zeros(Npumps, dtype=complex)
    for pp in range(Npumps):
        gp[pp] = gp_tune * gp0[pp] * np.exp(1j * phi_p[pp])

    # Call fcn to compute M and Minv
    M, M_inv = compute_M(omega0, nmodes, allmodes_freq, modes_freq, gamma, Npumps, gp, omega_p)

    # Compute Scattering Matrix S
    Id = np.identity(2 * nmodes)
    K = np.identity(2 * nmodes) * np.sqrt(gamma0_ext)
    Saa = 1j * K.dot(M_inv).dot(K) - Id

    # Compute the reference (zero-pump case)
    Npump_ref = 1
    g0ref = np.zeros((Npump_ref), dtype=complex)
    omega_pref = np.zeros((Npump_ref))
    omega_pref[0] = Delta * 2000
    M0ref, M0ref_inv = compute_M(omega0, nmodes, allmodes_freq, modes_freq, gamma, 1, g0ref, omega_pref)
    S0aa_ref = 1j * K.dot(M0ref_inv).dot(K) - Id
    S0a_ref = extract_small_S(S0aa_ref)
    S0num_ref = np.mean(np.abs(np.diag(S0a_ref)))  # Compute the mean of the diagonal elements'abs valu

    # Extract small S and normalize it with zero-pump case
    S = Saa / S0num_ref

    return S

def compute_S_2pmp(nmodes, gp0, phi_p, omega_p):
    # Compute the small S for Ai all'Italiana (S already normalized with the 0 pump case)

    # Physical parameters and Mode Basis definition
    omega0, Delta = physical_param()
    gp_tune, gamma_tune=fit_parameters_2pmp()
    # gp_tune = 200 #849.2462311557789
    # gamma_tune = 200*2.4 #1993.9698492462312

    modes_freq, modes_labels, allmodes_freq = generate_freq_vectors(nmodes, omega0, Delta)
    # Dissipation Rates
    gamma_int = 0.
    gamma_ext = 2 * np.pi * 100 * (10 ** 6) / (10 ** 9)  # [GHz]
    gamma0_ext = gamma_ext * gamma_tune
    gamma = gamma_int + gamma0_ext

    # Compute complex Pump Strength
    Npumps = len(gp0)
    gp = np.zeros(Npumps, dtype=complex)
    for pp in range(Npumps):
        gp[pp] = gp_tune * gp0[pp] * np.exp(1j * phi_p[pp])

    # Call fcn to compute M and Minv
    M, M_inv = compute_M(omega0, nmodes, allmodes_freq, modes_freq, gamma, Npumps, gp, omega_p)

    # Compute Scattering Matrix S
    Id = np.identity(2 * nmodes)
    K = np.identity(2 * nmodes) * np.sqrt(gamma0_ext)
    Saa = 1j * K.dot(M_inv).dot(K) - Id

    # Compute the reference (zero-pump case)
    Npump_ref = 1
    g0ref = np.zeros((Npump_ref), dtype=complex)
    omega_pref = np.zeros((Npump_ref))
    omega_pref[0] = Delta * 2000
    M0ref, M0ref_inv = compute_M(omega0, nmodes, allmodes_freq, modes_freq, gamma, 1, g0ref, omega_pref)
    S0aa_ref = 1j * K.dot(M0ref_inv).dot(K) - Id
    S0a_ref = extract_small_S(S0aa_ref)
    S0num_ref = np.mean(np.abs(np.diag(S0a_ref)))  # Compute the mean of the diagonal elements'abs valu

    # Extract small S and normalize it with zero-pump case
    S = extract_small_S(Saa) / S0num_ref

    return S

def compute_S_1pmp(nmodes, gp0, phi_p, omega_p):
    # Compute the small S for Ai all'Italiana (S already normalized with the 0 pump case)

    # Physical parameters and Mode Basis definition
    omega0, Delta = physical_param()
    gp_tune, gamma_tune=fit_parameters_1pmp()
    # gp_tune = 200 #849.2462311557789
    # gamma_tune = 200*2.4 #1993.9698492462312

    modes_freq, modes_labels, allmodes_freq = generate_freq_vectors(nmodes, omega0, Delta)
    # Dissipation Rates
    gamma_int = 0.
    gamma_ext = 2 * np.pi * 100 * (10 ** 6) / (10 ** 9)  # [GHz]
    gamma0_ext = gamma_ext * gamma_tune
    gamma = gamma_int + gamma0_ext

    # Compute complex Pump Strength
    Npumps = len(gp0)
    gp = np.zeros(Npumps, dtype=complex)
    for pp in range(Npumps):
        gp[pp] = gp_tune * gp0[pp] * np.exp(1j * phi_p[pp])

    # Call fcn to compute M and Minv
    M, M_inv = compute_M(omega0, nmodes, allmodes_freq, modes_freq, gamma, Npumps, gp, omega_p)

    # Compute Scattering Matrix S
    Id = np.identity(2 * nmodes)
    K = np.identity(2 * nmodes) * np.sqrt(gamma0_ext)
    Saa = 1j * K.dot(M_inv).dot(K) - Id

    # Compute the reference (zero-pump case)
    Npump_ref = 1
    g0ref = np.zeros((Npump_ref), dtype=complex)
    omega_pref = np.zeros((Npump_ref))
    omega_pref[0] = Delta * 2000
    M0ref, M0ref_inv = compute_M(omega0, nmodes, allmodes_freq, modes_freq, gamma, 1, g0ref, omega_pref)
    S0aa_ref = 1j * K.dot(M0ref_inv).dot(K) - Id
    S0a_ref = extract_small_S(S0aa_ref)
    S0num_ref = np.mean(np.abs(np.diag(S0a_ref)))  # Compute the mean of the diagonal elements'abs valu

    # Extract small S and normalize it with zero-pump case
    S = extract_small_S(Saa) / S0num_ref

    return S

def compute_bigS_1pmp(nmodes, gp0, phi_p, omega_p):
    # Compute the small S for Ai all'Italiana (S already normalized with the 0 pump case)

    # Physical parameters and Mode Basis definition
    omega0, Delta = physical_param()
    gp_tune, gamma_tune=fit_parameters_1pmp()
    # gp_tune = 200 #849.2462311557789
    # gamma_tune = 200*2.4 #1993.9698492462312

    modes_freq, modes_labels, allmodes_freq = generate_freq_vectors(nmodes, omega0, Delta)
    # Dissipation Rates
    gamma_int = 0.
    gamma_ext = 2 * np.pi * 100 * (10 ** 6) / (10 ** 9)  # [GHz]
    gamma0_ext = gamma_ext * gamma_tune
    gamma = gamma_int + gamma0_ext

    # Compute complex Pump Strength
    Npumps = len(gp0)
    gp = np.zeros(Npumps, dtype=complex)
    for pp in range(Npumps):
        gp[pp] = gp_tune * gp0[pp] * np.exp(1j * phi_p[pp])

    # Call fcn to compute M and Minv
    M, M_inv = compute_M(omega0, nmodes, allmodes_freq, modes_freq, gamma, Npumps, gp, omega_p)

    # Compute Scattering Matrix S
    Id = np.identity(2 * nmodes)
    K = np.identity(2 * nmodes) * np.sqrt(gamma0_ext)
    Saa = 1j * K.dot(M_inv).dot(K) - Id

    # Compute the reference (zero-pump case)
    Npump_ref = 1
    g0ref = np.zeros((Npump_ref), dtype=complex)
    omega_pref = np.zeros((Npump_ref))
    omega_pref[0] = Delta * 2000
    M0ref, M0ref_inv = compute_M(omega0, nmodes, allmodes_freq, modes_freq, gamma, 1, g0ref, omega_pref)
    S0aa_ref = 1j * K.dot(M0ref_inv).dot(K) - Id
    S0a_ref = extract_small_S(S0aa_ref)
    S0num_ref = np.mean(np.abs(np.diag(S0a_ref)))  # Compute the mean of the diagonal elements'abs valu

    # Extract small S and normalize it with zero-pump case
    S = Saa# / S0num_ref

    return S

def target_S_AiaI_3pmp_phi_0(nmodes):
    # Compute the small S for Ai all'Italiana (S already normalized with the 0 pump case)
    # Case 3pmp phi=0

    # Physical parameters and Mode Basis definition
    omega0, Delta = physical_param()

    # Pumping scheme definition
    Npumps = 3
    gp = np.zeros((Npumps))
    phi_p = np.zeros((Npumps))
    omega_p = np.zeros((Npumps))

    # Pump 1
    omega_p[0] = 2*omega0 - 4*Delta
    phi_p[0] = 0
    gp[0] = 1
    # Pump 2
    omega_p[1] = 2*omega0
    phi_p[1] = 0
    gp[1] = 1
    # Pump 3
    omega_p[2] = 2*omega0 + 4*Delta
    phi_p[2] = 0
    gp[2] = 1

    S=compute_S_3pmp(nmodes, gp, phi_p, omega_p)

    return S

def target_S_AiaI_3pmp_phi_pi(nmodes):
    # Compute the small S for Ai all'Italiana (S already normalized with the 0 pump case)
    # Case 3pmp phi=0

    # Physical parameters and Mode Basis definition
    omega0, Delta = physical_param()

    # Pumping scheme definition
    Npumps = 3
    gp = np.zeros((Npumps))
    phi_p = np.zeros((Npumps))
    omega_p = np.zeros((Npumps))

    # Pump 1
    omega_p[0] = 2 * omega0 - 4 * Delta
    phi_p[0] = np.pi
    gp[0] = 1
    # Pump 2
    omega_p[1] = 2 * omega0
    phi_p[1] = 0
    gp[1] = 1
    # Pump 3
    omega_p[2] = 2 * omega0 + 4 * Delta
    phi_p[2] = 0
    gp[2] = 1

    S = compute_S_3pmp(nmodes, gp, phi_p, omega_p)

    return S

def make_bigS_3pmp_phi(nmodes,phi):
    # Compute the small S for Ai all'Italiana (S already normalized with the 0 pump case)
    # Case 3pmp phi=0

    # Physical parameters and Mode Basis definition
    omega0, Delta = physical_param()

    # Pumping scheme definition
    Npumps = 3
    gp = np.zeros((Npumps))
    phi_p = np.zeros((Npumps))
    omega_p = np.zeros((Npumps))

    # Pump 1
    omega_p[0] = 2 * omega0 - 4 * Delta
    phi_p[0] = phi
    gp[0] = 1
    # Pump 2
    omega_p[1] = 2 * omega0
    phi_p[1] = 0
    gp[1] = 1
    # Pump 3
    omega_p[2] = 2 * omega0 + 4 * Delta
    phi_p[2] = 0
    gp[2] = 1

    S = compute_bigS_3pmp(nmodes, gp, phi_p, omega_p)

    return S

def target_S_AiaI_3pmp_phi(nmodes,phi):
    # Compute the small S for Ai all'Italiana (S already normalized with the 0 pump case)
    # Case 3pmp phi=0

    # Physical parameters and Mode Basis definition
    omega0, Delta = physical_param()

    # Pumping scheme definition
    Npumps = 3
    gp = np.zeros((Npumps))
    phi_p = np.zeros((Npumps))
    omega_p = np.zeros((Npumps))

    # Pump 1
    omega_p[0] = 2 * omega0 - 4 * Delta
    phi_p[0] = phi
    gp[0] = 1
    # Pump 2
    omega_p[1] = 2 * omega0
    phi_p[1] = 0
    gp[1] = 1
    # Pump 3
    omega_p[2] = 2 * omega0 + 4 * Delta
    phi_p[2] = 0
    gp[2] = 1

    S = compute_S_3pmp(nmodes, gp, phi_p, omega_p)

    return S

def target_S_AiaI_3pmp_phi2(nmodes,phi):
    # Compute the small S for Ai all'Italiana (S already normalized with the 0 pump case)
    # Case 3pmp phi=0

    # Physical parameters and Mode Basis definition
    omega0, Delta = physical_param()

    # Pumping scheme definition
    Npumps = 3
    gp = np.zeros((Npumps))
    phi_p = np.zeros((Npumps))
    omega_p = np.zeros((Npumps))

    # Pump 1
    omega_p[0] = 2 * omega0 - 4 * Delta
    phi_p[0] = 0
    gp[0] = 1
    # Pump 2
    omega_p[1] = 2 * omega0
    phi_p[1] = phi
    gp[1] = 1
    # Pump 3
    omega_p[2] = 2 * omega0 + 4 * Delta
    phi_p[2] = 0
    gp[2] = 1

    S = compute_S_3pmp(nmodes, gp, phi_p, omega_p)

    return S

def target_S_AiaI_2pmp(nmodes):
    # Compute the small S for Ai all'Italiana (S already normalized with the 0 pump case)
    # Case 3pmp phi=0

    # Physical parameters and Mode Basis definition
    omega0, Delta = physical_param()

    # Pumping scheme definition
    Npumps = 2
    gp = np.zeros((Npumps))
    phi_p = np.zeros((Npumps))
    omega_p = np.zeros((Npumps))

    # Pump 1
    omega_p[0] = 2 * omega0 - 2 * Delta
    phi_p[0] = 0
    gp[0] = 1
    # Pump 2
    omega_p[1] = 2 * omega0 + 2 * Delta
    phi_p[1] = 0
    gp[1] = 1

    S = compute_S_2pmp(nmodes, gp, phi_p, omega_p)

    return S

def target_S_AiaI_1pmp(nmodes):
    # Compute the small S for Ai all'Italiana (S already normalized with the 0 pump case)
    # Case 3pmp phi=0

    # Physical parameters and Mode Basis definition
    omega0, Delta = physical_param()

    # Pumping scheme definition
    Npumps = 1
    gp = np.zeros((Npumps))
    phi_p = np.zeros((Npumps))
    omega_p = np.zeros((Npumps))

    # Pump 1
    omega_p[0] = 2 * omega0
    phi_p[0] = 0
    gp[0] = 1

    S = compute_S_1pmp(nmodes, gp, phi_p, omega_p)

    return S

def compute_bigS_1pmp(nmodes, gp0, phi_p, omega_p):
    # Compute the small S for Ai all'Italiana (S already normalized with the 0 pump case)

    # Physical parameters and Mode Basis definition
    omega0, Delta = physical_param()
    gp_tune, gamma_tune=fit_parameters_1pmp()
    # gp_tune = 200 #849.2462311557789
    # gamma_tune = 200*2.4 #1993.9698492462312

    modes_freq, modes_labels, allmodes_freq = generate_freq_vectors(nmodes, omega0, Delta)
    # Dissipation Rates
    gamma_int = 0.
    gamma_ext = 2 * np.pi * 100 * (10 ** 6) / (10 ** 9)  # [GHz]
    gamma0_ext = gamma_ext * gamma_tune
    gamma = gamma_int + gamma0_ext

    # Compute complex Pump Strength
    Npumps = len(gp0)
    gp = np.zeros(Npumps, dtype=complex)
    for pp in range(Npumps):
        gp[pp] = gp_tune * gp0[pp] * np.exp(1j * phi_p[pp])

    # Call fcn to compute M and Minv
    M, M_inv = compute_M(omega0, nmodes, allmodes_freq, modes_freq, gamma, Npumps, gp, omega_p)

    # Compute Scattering Matrix S
    Id = np.identity(2 * nmodes)
    K = np.identity(2 * nmodes) * np.sqrt(gamma0_ext)
    Saa = 1j * K.dot(M_inv).dot(K) - Id

    # Compute the reference (zero-pump case)
    Npump_ref = 1
    g0ref = np.zeros((Npump_ref), dtype=complex)
    omega_pref = np.zeros((Npump_ref))
    omega_pref[0] = Delta * 2000
    M0ref, M0ref_inv = compute_M(omega0, nmodes, allmodes_freq, modes_freq, gamma, 1, g0ref, omega_pref)
    S0aa_ref = 1j * K.dot(M0ref_inv).dot(K) - Id
    S0a_ref = extract_small_S(S0aa_ref)
    S0num_ref = np.mean(np.abs(np.diag(S0a_ref)))  # Compute the mean of the diagonal elements'abs valu

    # Extract small S and normalize it with zero-pump case
    S = Saa / S0num_ref

    return S

def compute_bigS_1pmp_noref(nmodes, gp0, phi_p, omega_p):
    # Compute the small S for Ai all'Italiana (S already normalized with the 0 pump case)

    # Physical parameters and Mode Basis definition
    omega0, Delta = physical_param()
    gp_tune, gamma_tune=fit_parameters_1pmp()
    # gp_tune = 200 #849.2462311557789
    # gamma_tune = 200*2.4 #1993.9698492462312

    modes_freq, modes_labels, allmodes_freq = generate_freq_vectors(nmodes, omega0, Delta)
    # Dissipation Rates
    gamma_int = 0.
    gamma_ext = 2 * np.pi * 100 * (10 ** 6) / (10 ** 9)  # [GHz]
    gamma0_ext = gamma_ext * gamma_tune
    gamma = gamma_int + gamma0_ext

    # Compute complex Pump Strength
    Npumps = len(gp0)
    gp = np.zeros(Npumps, dtype=complex)
    for pp in range(Npumps):
        gp[pp] = gp_tune * gp0[pp] * np.exp(1j * phi_p[pp])

    # Call fcn to compute M and Minv
    M, M_inv = compute_M(omega0, nmodes, allmodes_freq, modes_freq, gamma, Npumps, gp, omega_p)

    # Compute Scattering Matrix S
    Id = np.identity(2 * nmodes)
    K = np.identity(2 * nmodes) * np.sqrt(gamma0_ext)
    Saa = 1j * K.dot(M_inv).dot(K) - Id

    # Compute the reference (zero-pump case)
    Npump_ref = 1
    g0ref = np.zeros((Npump_ref), dtype=complex)
    omega_pref = np.zeros((Npump_ref))
    omega_pref[0] = Delta * 2000
    M0ref, M0ref_inv = compute_M(omega0, nmodes, allmodes_freq, modes_freq, gamma, 1, g0ref, omega_pref)
    S0aa_ref = 1j * K.dot(M0ref_inv).dot(K) - Id
    S0a_ref = extract_small_S(S0aa_ref)
    S0num_ref = np.mean(np.abs(np.diag(S0a_ref)))  # Compute the mean of the diagonal elements'abs valu

    # Extract small S and normalize it with zero-pump case
    S = Saa# / S0num_ref

    return S, S0num_ref

def compute_bigS_3pmp_noref(nmodes, gp0, phi_p, omega_p):
    # Compute the small S for Ai all'Italiana (S already normalized with the 0 pump case)

    # Physical parameters and Mode Basis definition
    omega0, Delta = physical_param()
    gp_tune, gamma_tune=fit_parameters_3pmp()
    # gp_tune = 200 #849.2462311557789
    # gamma_tune = 200*2.4 #1993.9698492462312

    modes_freq, modes_labels, allmodes_freq = generate_freq_vectors(nmodes, omega0, Delta)
    # Dissipation Rates
    gamma_int = 0.
    gamma_ext = 2 * np.pi * 100 * (10 ** 6) / (10 ** 9)  # [GHz]
    gamma0_ext = gamma_ext * gamma_tune
    gamma = gamma_int + gamma0_ext

    # Compute complex Pump Strength
    Npumps = len(gp0)
    gp = np.zeros(Npumps, dtype=complex)
    for pp in range(Npumps):
        gp[pp] = gp_tune * gp0[pp] * np.exp(1j * phi_p[pp])

    # Call fcn to compute M and Minv
    M, M_inv = compute_M(omega0, nmodes, allmodes_freq, modes_freq, gamma, Npumps, gp, omega_p)

    # Compute Scattering Matrix S
    Id = np.identity(2 * nmodes)
    K = np.identity(2 * nmodes) * np.sqrt(gamma0_ext)
    Saa = 1j * K.dot(M_inv).dot(K) - Id

    # Compute the reference (zero-pump case)
    Npump_ref = 1
    g0ref = np.zeros((Npump_ref), dtype=complex)
    omega_pref = np.zeros((Npump_ref))
    omega_pref[0] = Delta * 2000
    M0ref, M0ref_inv = compute_M(omega0, nmodes, allmodes_freq, modes_freq, gamma, 1, g0ref, omega_pref)
    S0aa_ref = 1j * K.dot(M0ref_inv).dot(K) - Id
    S0a_ref = extract_small_S(S0aa_ref)
    S0num_ref = np.mean(np.abs(np.diag(S0a_ref)))  # Compute the mean of the diagonal elements'abs valu

    # Extract small S and normalize it with zero-pump case
    S = Saa #/ S0num_ref

    return S, S0num_ref

def make_bigS_1pmp_g(nmodes,g):
    # Compute the small S for Ai all'Italiana (S already normalized with the 0 pump case)
    # Case 3pmp phi=0

    # Physical parameters and Mode Basis definition
    omega0, Delta = physical_param()

    # Pumping scheme definition
    Npumps = 1
    gp = np.zeros((Npumps))
    phi_p = np.zeros((Npumps))
    omega_p = np.zeros((Npumps))

    # Pump 1
    omega_p[0] = 2 * omega0
    phi_p[0] = 0
    gp[0] = g

    S, S0num_ref = compute_bigS_1pmp_noref(nmodes, gp, phi_p, omega_p)

    return S, S0num_ref


def make_bigS_3pmp_g(nmodes,g, phi1=None):
    # Compute the big S for
    # Case 3pmp (Default: phi1=0)
    if (phi1==None):
        phi1=0

    # Physical parameters and Mode Basis definition
    omega0, Delta = physical_param()

    # Pumping scheme definition
    Npumps = 3
    gp = np.zeros((Npumps))
    phi_p = np.zeros((Npumps))
    omega_p = np.zeros((Npumps))

    # Pump 1
    omega_p[0] = 2 * omega0 - 4 * Delta
    phi_p[0] = phi1
    gp[0] = g
    # Pump 2
    omega_p[1] = 2 * omega0
    phi_p[1] = 0
    gp[1] = g
    # Pump 3
    omega_p[2] = 2 * omega0 + 4 * Delta
    phi_p[2] = 0
    gp[2] = g

    S, S0num_ref = compute_bigS_3pmp_noref(nmodes, gp, phi_p, omega_p)

    return S, S0num_ref


def make_bigS_4pmp_g(nmodes,g, phi1=None):
    # Compute the big S for
    # Case 4pmp (Default: phi1=0)
    if (phi1==None):
        phi1=0

    # Physical parameters and Mode Basis definition
    omega0, Delta = physical_param()

    # Pumping scheme definition
    Npumps = 4
    gp = np.zeros((Npumps))
    phi_p = np.zeros((Npumps))
    omega_p = np.zeros((Npumps))

    # Pump 1
    omega_p[0] = 2 * omega0 - 9 * Delta
    phi_p[0] = phi1
    gp[0] = g
    # Pump 2
    omega_p[1] = 2 * omega0 - 1* Delta
    phi_p[1] = 0
    gp[1] = g
    # Pump 3
    omega_p[2] = 2 * omega0 + 1 * Delta
    phi_p[2] = 0
    gp[2] = g
    # Pump 4
    omega_p[3] = 2 * omega0 + 9 * Delta
    phi_p[3] = 0
    gp[3] = g

    S, S0num_ref = compute_bigS_4pmp_noref(nmodes, gp, phi_p, omega_p)

    return S, S0num_ref


def make_bigS_4pmp_g_and_k(nmodes,g, k_array, phi1=None):
    # Compute the big S for 4 pmp and SqLattice
    # Case 4pmp (Default: phi1=0)
    if (phi1==None):
        phi1=0

    # Physical parameters and Mode Basis definition
    omega0, Delta = physical_param()

    # Pumping scheme definition
    Npumps = 4
    gp = np.zeros((Npumps))
    phi_p = np.zeros((Npumps))
    omega_p = np.zeros((Npumps))

    # Pump 1
    omega_p[0] = 2 * omega0 + k_array[0]* Delta
    phi_p[0] = phi1
    gp[0] = g
    # Pump 2
    omega_p[1] = 2 * omega0 + k_array[1]* Delta
    phi_p[1] = 0
    gp[1] = g
    # Pump 3
    omega_p[2] = 2 * omega0 + k_array[2] * Delta
    phi_p[2] = 0
    gp[2] = g
    # Pump 4
    omega_p[3] = 2 * omega0 + k_array[3] * Delta
    phi_p[3] = 0
    gp[3] = g
    print("k_array", k_array)
    print("omega_p", omega_p)
    S, S0num_ref = compute_bigS_4pmp_noref(nmodes, gp, phi_p, omega_p)

    return S, S0num_ref

def compute_bigS_4pmp_noref(nmodes, gp0, phi_p, omega_p):
    # Compute the small S for Ai all'Italiana (S already normalized with the 0 pump case)

    # Physical parameters and Mode Basis definition
    omega0, Delta = physical_param()
    gp_tune, gamma_tune=fit_parameters_3pmp()
    # gp_tune = 200 #849.2462311557789
    # gamma_tune = 200*2.4 #1993.9698492462312

    modes_freq, modes_labels, allmodes_freq = generate_freq_vectors(nmodes, omega0, Delta)
    # Dissipation Rates
    gamma_int = 0.
    gamma_ext = 2 * np.pi * 100 * (10 ** 6) / (10 ** 9)  # [GHz]
    gamma0_ext = gamma_ext * gamma_tune
    gamma = gamma_int + gamma0_ext

    # Compute complex Pump Strength
    Npumps = len(gp0)
    gp = np.zeros(Npumps, dtype=complex)
    for pp in range(Npumps):
        gp[pp] = gp_tune * gp0[pp] * np.exp(1j * phi_p[pp])

    # Call fcn to compute M and Minv
    M, M_inv = compute_M(omega0, nmodes, allmodes_freq, modes_freq, gamma, Npumps, gp, omega_p)

    # Compute Scattering Matrix S
    Id = np.identity(2 * nmodes)
    K = np.identity(2 * nmodes) * np.sqrt(gamma0_ext)
    Saa = 1j * K.dot(M_inv).dot(K) - Id

    # Compute the reference (zero-pump case)
    Npump_ref = 1
    g0ref = np.zeros((Npump_ref), dtype=complex)
    omega_pref = np.zeros((Npump_ref))
    omega_pref[0] = Delta * 2000
    M0ref, M0ref_inv = compute_M(omega0, nmodes, allmodes_freq, modes_freq, gamma, 1, g0ref, omega_pref)
    S0aa_ref = 1j * K.dot(M0ref_inv).dot(K) - Id
    S0a_ref = extract_small_S(S0aa_ref)
    S0num_ref = np.mean(np.abs(np.diag(S0a_ref)))  # Compute the mean of the diagonal elements'abs valu

    # Extract small S and normalize it with zero-pump case
    S = Saa #/ S0num_ref

    return S, S0num_ref


def compute_bigS_from_g(nmodes, gp0, omega_p, omega0=None, Delta=None):
    # Compute the small S for Ai all'Italiana (S already normalized with the 0 pump case)

    # Physical parameters and Mode Basis definition
    if ( (omega0 == None) or (Delta == None) ):
        omega0, Delta = physical_param()
    # gp_tune, gamma_tune=fit_parameters_3pmp()
    gp_tune = 24 	                             # Reference coupling strength
    gamma_over_g = 10.0                          # Dissipation-to-coupling ratio

    # Compute total decay rate
    gamma_tune      = gp_tune * gamma_over_g 
    
    modes_freq, modes_labels, allmodes_freq = generate_freq_vectors(nmodes, omega0, Delta)
    # Dissipation Rates
    gamma_int = 0.
    gamma_ext = 2 * np.pi * 100 * (10 ** 6) / (10 ** 9)  # [GHz]
    gamma0_ext = gamma_ext * gamma_tune
    gamma = gamma_int + gamma0_ext

    # Compute complex Pump Strength
    Npumps = len(gp0)
    gp = np.zeros(Npumps, dtype=complex)
    for pp in range(Npumps):
        gp[pp] = gp_tune * gp0[pp] 

    # Call fcn to compute M and Minv
    M, M_inv = compute_M(omega0, nmodes, allmodes_freq, modes_freq, gamma, Npumps, gp, omega_p)

    # Compute Scattering Matrix S
    Id = np.identity(2 * nmodes)
    K = np.identity(2 * nmodes) * np.sqrt(gamma0_ext)
    Saa = 1j * K.dot(M_inv).dot(K) - Id

    # Compute the reference (zero-pump case)
    Npump_ref = 1
    g0ref = np.zeros((Npump_ref), dtype=complex)
    omega_pref = np.zeros((Npump_ref))
    omega_pref[0] = Delta * 2000
    M0ref, M0ref_inv = compute_M(omega0, nmodes, allmodes_freq, modes_freq, gamma, 1, g0ref, omega_pref)
    S0aa_ref = 1j * K.dot(M0ref_inv).dot(K) - Id
    S0a_ref = extract_small_S(S0aa_ref)
    S0num_ref = np.mean(np.abs(np.diag(S0a_ref)))  # Compute the mean of the diagonal elements'abs valu

    # Extract small S and normalize it with zero-pump case
    S = Saa #/ S0num_ref

    return S, S0num_ref




def make_bigS_3pmp_1CStateOdd(nmodes,g, phi1=None):
    # Compute the big S for
    # Case 3pmp (Default: phi1=0)
    if (phi1==None):
        phi1=0

    # Physical parameters and Mode Basis definition
    omega0, Delta = physical_param()

    nmodes_new=2*nmodes+1

    # Pumping scheme definition
    Npumps = 3
    gp = np.zeros((Npumps))
    phi_p = np.zeros((Npumps))
    omega_p = np.zeros((Npumps))

    # Pump 1
    omega_p[0] = 2 * omega0 - 4 * Delta
    phi_p[0] = phi1
    gp[0] = g
    # Pump 2
    omega_p[1] = 2 * omega0
    phi_p[1] = 0
    gp[1] = g
    # Pump 3
    omega_p[2] = 2 * omega0 + 4 * Delta
    phi_p[2] = 0
    gp[2] = g

    S, S0num_ref = compute_bigS_3pmp_noref(nmodes_new, gp, phi_p, omega_p)

    return S, S0num_ref


def gluing_pixels_DctDst(xp_vec):
    Nquad,Npix = xp_vec.shape
    Nmod=Nquad//2
    pix_0_f = np.zeros((2 * Nmod))
    pix_0_t = np.zeros((2 * Nmod))
    pix_1_f = np.zeros((2 * Nmod))
    pix_1_t = np.zeros((2 * Nmod))
    pix_2T_f = np.zeros((2 * 2 * Nmod))
    xp_2T = np.zeros((2 * 2 * Nmod, Npix // 2))
    tti = 0
    for ti in range(0, Npix, 2):
        pix_0_f[0::2] = xp_vec[0::2, ti]
        pix_0_f[1::2] = xp_vec[1::2, ti]
        pix_1_f[0::2] = xp_vec[0::2, ti + 1]
        pix_1_f[1::2] = xp_vec[1::2, ti + 1]
        # anti-Trasf pix 0 (cos for x, sin for p)
        pix_0_t[0::2] = sci.fft.idct(pix_0_f[0::2])
        pix_0_t[1::2] = sci.fft.idst(pix_0_f[1::2])
        # anti-Trasf pix 1 (cos for x, sin for p)
        pix_1_t[0::2] = sci.fft.idct(pix_1_f[0::2])
        pix_1_t[1::2] = sci.fft.idst(pix_1_f[1::2])
        # glue pix 0 and pix 1
        pix_2T_t = np.concatenate((pix_0_t, pix_1_t))
        # print(pix_2T_t.shape)
        # trasf back the glued pixel
        pix_2T_f[0::2] = sci.fft.dct(pix_2T_t[0::2])
        pix_2T_f[1::2] = sci.fft.dst(pix_2T_t[1::2])
        # Save
        xp_2T[:, tti] = pix_2T_f
        tti += 1
    return xp_2T

def gluing_pixels_DFT(xp_vec):
    Nquad,Npix = xp_vec.shape
    Nmod=Nquad//2
    pix_0_f = np.zeros((2 * Nmod))
    px0_t_aa = np.zeros((2 * Nmod), dtype=complex)
    px0_f_aa = np.zeros((2 * Nmod), dtype=complex)
    pix_1_f = np.zeros((2 * Nmod))
    px1_t_aa = np.zeros((2 * Nmod), dtype=complex)
    px1_f_aa = np.zeros((2 * Nmod), dtype=complex)
    px_2T_f_aa = np.zeros((2 * 2 * Nmod), dtype=complex)
    pix_2T_f = np.zeros((2 * 2 * Nmod))
    xp_2T = np.zeros((2 * 2 * Nmod, Npix // 2))

    # Change of basis Transformation Matrices: a,a* --U--> x,p
    U_2by2 = (1 / np.sqrt(2)) * np.array([[1, 1j],
                                          [1, -1j]])  # \vec{a} = U\vec{x}
    Udag_2by2 = (1 / np.sqrt(2)) * np.array([[1, 1],
                                             [-1j, 1j]])  # \vec{x} = Udag\vec{a}
    U_N = np.kron(np.eye(Nmod, dtype=complex), U_2by2)
    Udag_N = np.linalg.inv(U_N)
    U_2N = np.kron(np.eye(2*Nmod, dtype=complex), U_2by2)
    Udag_2N = np.linalg.inv(U_2N)

    tti = 0
    for ti in range(0, Npix, 2):
        pix_0_f[0::2] = xp_vec[0::2, ti]
        pix_0_f[1::2] = xp_vec[1::2, ti]
        pix_1_f[0::2] = xp_vec[0::2, ti + 1]
        pix_1_f[1::2] = xp_vec[1::2, ti + 1]
        # anti-Transf. pix 0
        px0_f_aa= (U_N.dot(pix_0_f).dot(Udag_N))  #from xi,pi to ai,ai^*
        px0_t_aa[0::2] = sci.fft.ifft(px0_f_aa[0::2]) #for ai
        px0_t_aa[1::2] = np.conjugate(px0_t_aa[0::2])#sci.fft.ifft(px0_f_aa[1::2]) # for ai^*
        # anti-Transf. pix 1
        px1_f_aa = (U_N.dot(pix_1_f).dot(Udag_N))  #from xi,pi to ai,ai^*
        px1_t_aa[0::2] = sci.fft.ifft(px1_f_aa[0::2])  # for ai
        px1_t_aa[1::2] = np.conjugate(px1_t_aa[0::2])#sci.fft.ifft(px1_f_aa[1::2])  # for ai^*
        # glue pix 0 and pix 1
        px_2T_t_aa = np.concatenate((px0_t_aa, px1_t_aa))
        # print(px0_t_aa.shape, px1_t_aa.shape, px_2T_t_aa.shape)
        # Transf. back the glued pixel
        px_2T_f_aa[0::2] = sci.fft.fft(px_2T_t_aa[0::2])
        px_2T_f_aa[1::2] = np.conjugate(px_2T_f_aa[0::2] ) #sci.fft.fft(px_2T_t_aa[1::2])
        pix_2T_f = np.real( (Udag_2N.dot(px_2T_f_aa).dot(U_2N)) )    #from ai,ai^* to xi,pi
        # Save
        xp_2T[:, tti] = pix_2T_f
        tti += 1
    return xp_2T



### PyPump related functions for the inverse problem

def g_from_M(omega_0, Delta, Nmodes, g1_value, M):
    # Compute the g_k and omega_k from the M matrix
    # g = from PyPump
    # return g_k, omega_k
    
    # Build matrix without diagonal for inner-product calculations
    diag_vec = np.diag(M)
    n = len(diag_vec)
    Nmodes = n // 2
    M_no_diag = M.copy()
    np.fill_diagonal(M_no_diag, 0)  # Zero out diagonal entries

    
    
    return 1.0  # Placeholder value, replace with actual computation if needed
