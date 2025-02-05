# -*- coding: utf-8 -*-
"""
Description: 

Last update: 03/18/2019
Version: 1.0
Author: afernandezcanosa@anl.gov
"""

"""
Parameters of the plots
"""

import matplotlib.pyplot as plt
import numpy as np

"""
Global properties of the plots
"""

class Plots(object):
    
    def __init__(self):
        self.figs_props = {
                'fig_s' : (9,6),
                'font_s' : 14,
                'font_w' : 'bold',
                'lw' : 1.75,
                'leg_prop' : {"size": 13}
        }

    def service_power(self, time, power_service, power_request, ts, dt, seconds_of_simulation):   
        plt.figure(figsize = self.figs_props['fig_s'])
        plt.title(self.get_plot_title(ts, dt, seconds_of_simulation),
                  fontsize = self.figs_props['font_s'] + 1, fontweight = self.figs_props['font_w'])
        plt.step(time - time[0], power_service, color = 'k', linewidth = self.figs_props['lw'], label = 'Service')
        plt.step(time - time[0], power_request, color = 'r', linewidth = self.figs_props['lw'], label = 'Request')
        plt.grid()
        plt.legend(prop = self.figs_props['leg_prop'])
        plt.xlim([0,max(time) - time[0]])
        plt.xlabel('$\Delta t$ (sec)', fontsize = self.figs_props['font_s'], fontweight = self.figs_props['font_w'])
        plt.ylabel('Service Power (kW)', fontsize = self.figs_props['font_s'], fontweight = self.figs_props['font_w'])
    
    
    def power_to_grid(self,time, power_response, power_baseline, power_request, ts, dt, seconds_of_simulation):
        plt.figure(figsize = self.figs_props['fig_s'])
        plt.title(self.get_plot_title(ts, dt, seconds_of_simulation),
                  fontsize=self.figs_props['font_s'] + 1, fontweight=self.figs_props['font_w'])
        plt.plot(np.arange(0,seconds_of_simulation), power_baseline, color = 'b', linewidth = self.figs_props['lw'], label = 'Baseline')
        plt.step(time - time[0], power_response, color = 'k', linewidth = self.figs_props['lw'], label = 'Response')
        plt.step(time - time[0], power_baseline[time] + power_request, color = 'r', linewidth = self.figs_props['lw'], label = 'Baseline + Request')
        plt.grid()
        plt.legend(prop = self.figs_props['leg_prop'])
        plt.xlim([0,max(time) - time[0]])
        plt.xlabel('$\Delta t$ (sec)', fontsize = self.figs_props['font_s'], fontweight = self.figs_props['font_w'])
        plt.ylabel('Power (kW)', fontsize = self.figs_props['font_s'], fontweight = self.figs_props['font_w'])
    
    
    def energy_fleet(self,time, energy_stored, ts, dt, seconds_of_simulation):    
        plt.figure(figsize = self.figs_props['fig_s'])
        plt.title(self.get_plot_title(ts, dt, seconds_of_simulation),
                  fontsize=self.figs_props['font_s'] + 1, fontweight=self.figs_props['font_w'])
        plt.plot(time - time[0], energy_stored*1e-6, color = 'b', linewidth = self.figs_props['lw'])
        plt.grid()
        plt.xlim([0,max(time) - time[0]])
        plt.xlabel('$\Delta t$ (sec)', fontsize = self.figs_props['font_s'], fontweight = self.figs_props['font_w'])
        plt.ylabel('Energy stored (GW.h)', fontsize = self.figs_props['font_s'], fontweight = self.figs_props['font_w'])
        
        
    def state_of_charge(self, time, SOC_fleet_time, SOC_right_away, SOC_midnight, SOC_tcin, ts, dt, seconds_of_simulation):
        plt.figure(figsize = self.figs_props['fig_s'])
        plt.title(self.get_plot_title(ts, dt, seconds_of_simulation),
                  fontsize=self.figs_props['font_s'] + 1, fontweight=self.figs_props['font_w'])
        plt.plot(time - time[0], SOC_fleet_time*100, color = 'b', linewidth = self.figs_props['lw'], label = 'Fleet')
        plt.plot(time - time[0], SOC_right_away*100, 'r--', linewidth = self.figs_props['lw'], label = 'Right-away')
        plt.plot(time - time[0], SOC_midnight*100, 'k--', linewidth = self.figs_props['lw'], label = 'Midnight')
        plt.plot(time - time[0], SOC_tcin*100, 'c--', linewidth = self.figs_props['lw'], label = 'TCIN')
        plt.grid()
        plt.legend(prop = self.figs_props['leg_prop'])
        plt.xlim([0,max(time) - time[0]])
        plt.xlabel('$\Delta t$ (sec)', fontsize = self.figs_props['font_s'], fontweight = self.figs_props['font_w'])
        plt.ylabel('SOC (%)', fontsize = self.figs_props['font_s'], fontweight = self.figs_props['font_w'])
        
    def efficiency(self, time, eff_charge, eff_discharge, ts, dt, seconds_of_simulation):
        plt.figure(figsize = self.figs_props['fig_s'])
        plt.title(self.get_plot_title(ts, dt, seconds_of_simulation),
                  fontsize=self.figs_props['font_s'] + 1, fontweight=self.figs_props['font_w'])
        plt.plot(time - time[0], eff_charge, color = 'b', linewidth = self.figs_props['lw'], label = 'Efficiency Charging')
        plt.plot(time - time[0], eff_discharge, color = 'r', linewidth = self.figs_props['lw'], label = 'Efficiency Discharging')
        plt.grid()
        plt.legend(prop = self.figs_props['leg_prop'])
        plt.xlim([0,max(time) - time[0]])
        plt.xlabel('$\Delta t$ (sec)', fontsize = self.figs_props['font_s'], fontweight = self.figs_props['font_w'])
        plt.ylabel(r'$e_{in, out}$ (%)', fontsize = self.figs_props['font_s'], fontweight = self.figs_props['font_w'])

    def get_plot_title(self, ts, dt, seconds_of_simulation):
        title = 'Initial hour of request: {}:{}:{}'.format(ts.hour, ts.minute, ts.second) +\
                '| {} hours of simulation'.format(round(seconds_of_simulation/3600)) +\
                '| dt = {} min'.format(round(dt/60))

        if 60 <= seconds_of_simulation < 3600:
            title = 'Initial hour of request: {}:{}:{}'.format(ts.hour, ts.minute, ts.second) +\
                    '| {} minutes of simulation'.format(round(seconds_of_simulation/60)) +\
                    '| dt = {} sec'.format(round(dt))
        elif seconds_of_simulation < 60:
            title = 'Initial hour of request: {}:{}:{}'.format(ts.hour, ts.minute, ts.second) +\
                    '| {} seconds of simulation'.format(round(seconds_of_simulation)) +\
                    '| dt = {} sec'.format(round(dt))

        return title
