from __future__ import absolute_import, unicode_literals

from django.views.generic.edit import CreateView, UpdateView
from django.views.generic import DetailView
from .models import Output, LogFrame, Indicator, SubIndicator
from .forms import (OutputForm, IndicatorFormSet, SubIndicatorForm,
                    BaseInlineFormSetWithEmpty)


class OutputBase(object):
    model = Output
    form_class = OutputForm
    context_object_name = 'output'
    template_name = 'logframe/output_edit_form.html'

    def get_context_data(self, **kwargs):
        context = super(OutputBase, self).get_context_data(**kwargs)
        context['milestones'] = self.get_object().log_frame.milestone_set.all()
        context['indicators'] = self.create_indicator_formset()
        return context

    def create_indicator_formset(self, output=None):
        if output is None:
            output = self.get_object()

        indicator_formset = IndicatorFormSet(
            data=(self.request.POST if self.request.method == 'POST' else None),
            instance=output,
            prefix='indicator_set_ind',
            initial=[
                {
                    'name': '',
                    'description': '',
                },
            ])

        for i, form in enumerate(indicator_formset):
            indicator = form.instance
            indicator.output = output

            # Subclass ModelForm for SubIndicator, to populate new (empty)
            # instances of SubIndicator with the correct Indicator, so that
            # they can get their Milestones.
            class CustomSubIndicatorForm(SubIndicatorForm):

                def __init__(self, instance=None, **kwargs):
                    if instance is None:
                        instance = SubIndicator(indicator=indicator)
                    super(CustomSubIndicatorForm, self).__init__(
                        instance=instance, **kwargs)

            from django.forms.models import inlineformset_factory
            SubIndicatorFormSet = inlineformset_factory(
                Indicator, SubIndicator, extra=0, form=CustomSubIndicatorForm,
                formset=BaseInlineFormSetWithEmpty)

            if form.empty:
                i = '__prefix__'
            form.subindicators = SubIndicatorFormSet(
                data=(self.request.POST if self.request.method == 'POST' else None),
                instance=indicator,
                prefix="ind-%s_subindicator_set_subind" % i,
                initial=[
                    {'indicator_id': indicator.id}
                ])
            for j, sif in enumerate(form.subindicators):
                subindicator = sif.instance
                from .forms import TargetFormSet
                sif.targets = TargetFormSet(
                    queryset=subindicator.targets_fake_queryset,
                    instance=subindicator,
                    prefix="subindicator_%s_%d_targets" % (i, j))

        return indicator_formset

    def get_success_url(self):
        from django.core.urlresolvers import reverse
        return reverse('logframe-output-update', kwargs={'pk': self.object.pk})

    def form_valid(self, form):
        indicator_formset = self.create_indicator_formset()
        if not indicator_formset.is_valid():
            return self.form_invalid(form)

        if form.instance.order is None:
            from django.db.models import Max
            max_order = form.instance.log_frame.output_set.aggregate(Max('order'))['order__max']
            if max_order is None:
                new_order = 1
            else:
                new_order = max_order + 1
            form.instance.order = new_order

        # save the Output object before its dependents:
        response = super(OutputBase, self).form_valid(form)
        # recreate the formset now that the Output has a PK to attach to
        indicator_formset = self.create_indicator_formset(self.object)
        if not indicator_formset.is_valid():
            # we validated all the parameters earlier!
            raise AssertionError('The formset was valid but no longer is')
        indicator_formset.save()
        for form in indicator_formset:
            # TODO: add stuff for when forms aren't valid
            if form.subindicators.is_valid():
                form.subindicators.save()
                for sif in form.subindicators:
                    if sif.targets.is_valid():
                        sif.targets.save()
        return response


class OutputCreate(OutputBase, CreateView):
    # We should really create the Output object in the database, with a
    # foreign key back to its own LogFrame before we start editing it; or
    # else find a way to pass the correct LogFrame ID into this view and
    # validate it here (same owner etc.) This is a stopgap until we have
    # real support for creating LogFrames in the web interface.
    def __init__(self, **kwargs):
        super(OutputCreate, self).__init__(**kwargs)
        # TODO: the logframe id should be an argument to the view
        self.default_log_frame = LogFrame.objects.first()

    def get_form_kwargs(self):
        kwargs = super(OutputCreate, self).get_form_kwargs()
        kwargs['instance'] = self.get_object()
        return kwargs

    def get_object(self):
        return Output(log_frame=self.default_log_frame)


class OutputUpdate(OutputBase, UpdateView):
    pass


class Overview(DetailView):
    model = LogFrame
    template_name = 'logframe/logframe_overview.html'


class IndicatorMonitor(UpdateView):
    model = Indicator
    template_name = 'logframe/indicator_monitor.html'
