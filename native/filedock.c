#include <gtk/gtk.h>
static GDBusNodeInfo *info;
static GDBusConnection *bus;
static guint registration;
static const char *xml="<node><interface name='io.github.nirisidecar.FileDock'><method name='List'><arg type='a(usbb)' direction='out'/></method><method name='Manage'><arg type='u' direction='in'/><arg type='b' direction='in'/></method><method name='Show'><arg type='u' direction='in'/></method><method name='Hide'><arg type='u' direction='in'/></method></interface></node>";
static gboolean file_window(GtkWindow *w) { return g_str_has_prefix(G_OBJECT_TYPE_NAME(w), "NautilusWindow"); }
static gboolean has_popup(GtkWidget *w) {
 if (GTK_IS_POPOVER(w) && gtk_widget_get_mapped(w)) return TRUE;
 for(GtkWidget *c=gtk_widget_get_first_child(w);c;c=gtk_widget_get_next_sibling(c)) if(has_popup(c))return TRUE;
 return FALSE;
}
static gboolean hide_later(gpointer data) {
 GtkWindow *w=data;
 g_object_set_data(G_OBJECT(w),"filedock-timer",NULL);
 GtkEventControllerMotion *m=g_object_get_data(G_OBJECT(w),"filedock-motion");
 if(!gtk_event_controller_motion_contains_pointer(m) && !has_popup(GTK_WIDGET(w))) {
  gboolean modal=FALSE; GList *all=gtk_window_list_toplevels();
  for(GList *l=all;l;l=l->next) if(gtk_window_get_transient_for(l->data)==w && gtk_widget_get_visible(l->data))modal=TRUE;
  g_list_free(all);
  if(!modal)gtk_widget_set_visible(GTK_WIDGET(w),FALSE);
 }
 return G_SOURCE_REMOVE;
}
static void cancel(GtkEventControllerMotion *m, double x,double y,gpointer data) {
 guint t=GPOINTER_TO_UINT(g_object_get_data(G_OBJECT(data),"filedock-timer"));
 if(t){g_source_remove(t);g_object_set_data(G_OBJECT(data),"filedock-timer",NULL);}
}
static void leave(GtkEventControllerMotion *m,gpointer data) {
 GdkModifierType state=gtk_event_controller_get_current_event_state(GTK_EVENT_CONTROLLER(m));
 if(g_object_get_data(G_OBJECT(data),"filedock-unmanaged"))return;
 if(state & (GDK_BUTTON1_MASK|GDK_BUTTON2_MASK|GDK_BUTTON3_MASK)) return;
 cancel(m,0,0,data);
 guint t=g_timeout_add_full(G_PRIORITY_DEFAULT,650,hide_later,g_object_ref(data),g_object_unref);
 g_object_set_data(G_OBJECT(data),"filedock-timer",GUINT_TO_POINTER(t));
}
static void method(GDBusConnection *c,const char *sender,const char *path,const char *iface,const char *name,GVariant *args,GDBusMethodInvocation *inv,gpointer data) {
 GList *all=gtk_window_list_toplevels();
 if(!g_strcmp0(name,"List")) {
  GVariantBuilder b;g_variant_builder_init(&b,G_VARIANT_TYPE("a(usbb)"));
  for(GList *l=all;l;l=l->next){GtkWindow *w=l->data;if(file_window(w))g_variant_builder_add(&b,"(usbb)",gtk_application_window_get_id(GTK_APPLICATION_WINDOW(w)),gtk_window_get_title(w)?gtk_window_get_title(w):"文件",gtk_widget_get_visible(GTK_WIDGET(w)),!g_object_get_data(G_OBJECT(w),"filedock-unmanaged"));}
  g_dbus_method_invocation_return_value(inv,g_variant_new("(a(usbb))",&b));
 } else {
  guint id;gboolean managed=TRUE; if(!g_strcmp0(name,"Manage"))g_variant_get(args,"(ub)",&id,&managed);else g_variant_get(args,"(u)",&id);
  for(GList *l=all;l;l=l->next){GtkWindow *w=l->data;if(file_window(w)&&gtk_application_window_get_id(GTK_APPLICATION_WINDOW(w))==id){cancel(NULL,0,0,w);if(!g_strcmp0(name,"Manage"))g_object_set_data(G_OBJECT(w),"filedock-unmanaged",managed?NULL:GINT_TO_POINTER(1));else if(!g_strcmp0(name,"Show"))gtk_window_present(w);else { GtkEventControllerMotion *m=g_object_get_data(G_OBJECT(w),"filedock-motion");if(!m || (!gtk_event_controller_motion_contains_pointer(m) && !has_popup(GTK_WIDGET(w))))gtk_widget_set_visible(GTK_WIDGET(w),FALSE);}}}
  g_dbus_method_invocation_return_value(inv,NULL);
 }
 g_list_free(all);
}
static const GDBusInterfaceVTable vtable={.method_call=method};
static gboolean scan(gpointer unused) {
 GList *all=gtk_window_list_toplevels();
 for(GList *l=all;l;l=l->next){GtkWindow *w=l->data;
  if(!file_window(w)||g_object_get_data(G_OBJECT(w),"filedock-motion"))continue;
  GtkEventController *m=gtk_event_controller_motion_new();
  gtk_event_controller_set_propagation_phase(m,GTK_PHASE_CAPTURE);
  g_signal_connect(m,"enter",G_CALLBACK(cancel),w);g_signal_connect(m,"leave",G_CALLBACK(leave),w);
  g_object_set_data(G_OBJECT(w),"filedock-motion",m);gtk_widget_add_controller(GTK_WIDGET(w),m);
 }
 g_list_free(all);
 if(!registration){
  GError *err=NULL;
  if(!bus)bus=g_bus_get_sync(G_BUS_TYPE_SESSION,NULL,&err);
  if(bus){if(!info)info=g_dbus_node_info_new_for_xml(xml,NULL);registration=g_dbus_connection_register_object(bus,"/FileDock",info->interfaces[0],&vtable,NULL,NULL,&err);if(registration)g_bus_own_name_on_connection(bus,"io.github.nirisidecar.FileDock",G_BUS_NAME_OWNER_FLAGS_NONE,NULL,NULL,NULL,NULL);}
  if(err){g_warning("FileDock: %s",err->message);g_error_free(err);}
 }
 return G_SOURCE_CONTINUE;
}
__attribute__((constructor)) static void init(void){char *exe=g_file_read_link("/proc/self/exe",NULL);gboolean enabled=exe && g_str_has_suffix(exe,"/nautilus");g_free(exe);if(enabled)g_timeout_add(250,scan,NULL);}
